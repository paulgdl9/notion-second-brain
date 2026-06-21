# Depot n8n Raspberry Pi

Ce depot documente et versionne la configuration n8n hebergee sur le Raspberry Pi dans `/SSD/n8n`.

Il sert a garder sous Git tout ce qui decrit le systeme, tout en laissant les secrets et l'etat runtime uniquement sur la machine.

## Architecture

Le systeme est compose de quatre briques principales :

- `n8n`, lance par Docker Compose, expose les workflows via `N8N_PUBLIC_URL`.
- `cloudflared`, lance par Docker Compose, maintient le tunnel Cloudflare vers n8n.
- `memo-bridge`, lance par systemd, expose une API locale sur le Raspberry Pi pour enrichir ou generer du contenu avec Claude.
- Notion, utilise comme base `Inbox IA` et comme destination du Daily Brief.

Flux de capture :

```text
memo.sh / iOS Shortcut / curl
  -> ${N8N_CAPTURE_URL}
  -> workflow Capture -> Notion
  -> memo-bridge /summarize
  -> Notion Inbox IA
```

Flux Daily Brief :

Le Daily Brief est un **copilote orienté objectifs** : il part des Objectifs (DB), pas des
captures. Il tourne tous les jours, même sans nouvelle capture. Il propose 1-3 tâches qui
atterrissent dans la DB Tâches, relit les tâches encore ouvertes et exploite les tâches passées à
`Fait` dans les trois derniers jours pour proposer une suite logique (boucle de progression).

Le workflow compte **22 nœuds**, heartbeat compris.

Flux de veille automatique :

```text
Schedule n8n 6h10
  -> lire les URL déjà présentes dans Inbox IA
  -> lire les flux configurés par WATCH_RSS_FEEDS
  -> scorer avec WATCH_KEYWORDS et les limites WATCH_*
  -> dédupliquer et limiter le volume
  -> memo-bridge /summarize
  -> Notion Inbox IA (Status=Inbox)
  -> Daily Brief à 7h
```

La sélection est volontairement limitée pour ne pas noyer le brief. Les sources et les pondérations
sont modifiables dans les nœuds `Sources RSS` et `Filtrer et classer` du workflow de veille.

```text
Schedule n8n 7h
  -> Inbox IA — pages (Notion getAll ; alwaysOutputData pour tourner même Inbox vide)
  -> Préparer (filtre Status=Inbox ; renvoie toujours 1 item, items[] possiblement vide)
  -> Notes — blocs (blocs de la page Notes : section Journal récent)
  -> Contexte système — blocs (profil, projets, priorités et règles dynamiques)
  -> Objectifs — actifs (Notion getAll DB Objectifs ; executeOnce + alwaysOutputData)
  -> Tâches — ouvertes (Notion getAll DB Tâches ; executeOnce + alwaysOutputData)
  -> Enrichir payload (construit {date, items, context, system_context, objectives, open_tasks, completed_tasks})
  -> memo-bridge /brief (Sonnet+Codex fallback ; renvoie aussi engine + context_source)
  -> Brief fallback si Claude KO (passe blocks si ok ; génère brief minimaliste si KO)
       |-> Brief: 1er bloc (Notion getAll page Daily Brief, executeOnce -> 1er bloc = en-tête permanent)
       |     -> Payload écriture (Code: construit {children:[divider,...blocks], after:<id 1er bloc>})
       |          -> Notion: écrire le brief (PATCH children avec `after` -> insertion en HAUT)
       |               |-> IDs à traiter -> Marquer Briefed (Status=Briefed + Briefed At)
       |               \-> Tâches à créer -> Créer Tâches (crée les tâches du jour dans la DB Tâches)
       \-> Détecter dégradation (Code: engine=claude → rien ; engine=codex|none → passe un item)
             -> Alerte Telegram (envoie un message au chat configuré)

Branche parallèle depuis Tâches — ouvertes :
  -> Tâches périmées (filtre âge > STALE_DAYS=7j)
       -> Abandonner tâches (Notion update Statut=Abandonnée)
```

Insertion en haut : l'API Notion `append children` ne sait pas prépendre, mais accepte un paramètre
`after: <block_id>`. La page Daily Brief a un **en-tête permanent** comme 1er bloc
(« 🗓️ Daily Briefs — le plus récent en haut »). Le workflow lit ce 1er bloc au runtime et insère le
nouveau brief juste après -> le plus récent reste en haut. Si l'en-tête est supprimé, le brief
retombe en bas (fallback sans `after`) : ne pas supprimer ce 1er bloc.

## Fichiers importants

- `docker-compose.yml` : lance `n8n` et `cloudflared`.
- `.env.example` : modele des variables attendues. Ce fichier est safe a commit.
- `/SSD/n8n/.env` : fichier reel de secrets sur le Raspberry Pi. Il ne doit jamais etre commit.
- `bridge/memo-bridge.py` : serveur HTTP local utilise par n8n ; `/summarize` et `/brief` essaient
  Claude puis Codex avant leur fallback local.
- `bridge/memo-summarize` : wrapper CLI Claude pour `/summarize`.
- `bridge/memo.sh` : helper shell pour capturer rapidement du texte vers n8n.
- `systemd/memo-bridge.service` : unite systemd durcie pour lancer le bridge.
- `systemd/n8n-monitor.{service,timer}` : watchdog hôte indépendant de n8n.
- `scripts/monitor-system.py` : vérifie services et heartbeat, avec alertes dédupliquées.
- `scripts/rotate-secrets.sh` : script utilitaire pour recharger les services apres rotation.
- `workflows/` : exports JSON des workflows n8n.
- `backups/` : backups locaux du Raspberry Pi, ignores par Git.

## Source unique des secrets

Le fichier source de verite est :

```bash
/SSD/n8n/.env
```

Ce fichier est lu directement par :

- Docker Compose, via `env_file: ./.env`, pour injecter les variables dans le conteneur n8n.
- Docker Compose lui-meme, pour interpoler `${CLOUDFLARED_TOKEN}` dans la commande cloudflared.
- `memo-bridge.service`, via `EnvironmentFile=/SSD/n8n/.env`.
- `bridge/memo.sh`, qui lit `CAPTURE_TOKEN` et `N8N_CAPTURE_URL` dans `/SSD/n8n/.env`.
- `scripts/monitor-system.py`, qui lit la configuration Telegram et les seuils de supervision.

Il ne doit pas y avoir de copie active des tokens ailleurs. Les anciens chemins `secrets/common.env`, `bridge/memo-bridge.env` et `bridge/webhook-token.txt` ne sont plus utilises.

## Role des variables dans `.env`

### `MEMO_TOKEN`

Token d'authentification interne entre n8n et `memo-bridge`.

n8n l'utilise dans les nodes HTTP :

```text
Authorization: Bearer <MEMO_TOKEN>
```

Le bridge compare ce bearer avec `MEMO_TOKEN` avant d'accepter les routes :

- `POST /summarize`
- `POST /brief`

Impact si ce token est faux ou absent : les workflows n8n ne peuvent plus appeler le bridge et les nodes `Memo Bridge` renvoient une erreur d'autorisation.

### `CAPTURE_TOKEN`

Token d'authentification du webhook public de capture.

Les clients externes doivent l'envoyer dans :

```text
X-Capture-Token: <CAPTURE_TOKEN>
```

Le workflow `Capture -> Notion (Inbox IA)` compare ce header a `$env.CAPTURE_TOKEN`. Sans token valide, il repond :

```json
{"ok": false, "error": "unauthorized"}
```

Impact si ce token est faux ou absent : les raccourcis iOS, `memo.sh` et les appels curl ne peuvent plus capturer dans Notion.

### `MEMO_PORT`

Port local ecoute par `memo-bridge`.

Valeur actuelle attendue :

```text
8088
```

n8n appelle le bridge via `MEMO_BRIDGE_URL`. Aucun hôte ou port n'est codé dans les workflows.

### `CLOUDFLARED_TOKEN`

Token Cloudflare Tunnel utilise par le conteneur `cloudflared`.

Il authentifie le tunnel qui publie l'URL configurée dans `N8N_PUBLIC_URL`.

Ce n'est pas un token applicatif n8n, ni un token pour les webhooks. Il sert uniquement a connecter le conteneur `cloudflared` au tunnel Cloudflare configure dans ton compte.

Impact si ce token est faux ou absent : n8n peut encore tourner localement, mais l'URL publique ne sera plus exposée.

## Rotation des secrets

Editer `/SSD/n8n/.env`, puis recharger les consommateurs :

```bash
cd /SSD/n8n
docker compose up -d n8n
sudo systemctl restart memo-bridge.service
```

Verification rapide :

```bash
systemctl is-active memo-bridge.service
docker ps --format '{{.Names}} {{.Status}}' | grep -E '^(n8n|cloudflared) '
```

Tester le webhook sans token :

```bash
. ./.env
curl -sS -i -X POST "$N8N_CAPTURE_URL" \
  -H 'Content-Type: application/json' \
  -d '{"source":"Manual","text":"unauthorized check"}'
```

Il doit repondre `401`.

Tester le bridge local :

```bash
cd /SSD/n8n
. ./.env
curl -sS -X POST http://127.0.0.1:${MEMO_PORT}/summarize \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer ${MEMO_TOKEN}" \
  -d '{"source":"Manual","text":"health check"}'
```

## Regles Git

Avant chaque commit :

```bash
git status --short
git diff --cached --name-status
git grep --cached -n -E '(Bearer [0-9a-f]{20,}|MEMO_TOKEN=[0-9a-f]|CAPTURE_TOKEN=[0-9a-f]|CLOUDFLARED_TOKEN=eyJhIjoi|eyJhIjoi)' || true
```

Ne jamais commit :

- `/SSD/n8n/.env`
- `backups/`
- anciens exports de workflows contenant des tokens en clair
- fichiers temporaires generes par Python ou Docker

## Exporter les workflows n8n

Les exports versionnes doivent venir de l'instance n8n courante :

```bash
scripts/export-workflows.sh
```

Le script retire les métadonnées de propriétaire et remplace l'ID local du credential Notion par
`__NOTION_CREDENTIAL_ID__`. `scripts/import-workflows.sh` effectue l'opération inverse à partir de
`N8N_NOTION_CREDENTIAL_ID`, importe, publie, puis redémarre n8n.

### ⚠️ Versioning n8n : publier après chaque modif MCP

n8n epingle une **version publiee** (`activeVersionId`) pour les executions schedule/trigger. Une
modification via l'API/MCP (`update_workflow`) cree une nouvelle version **draft** mais ne la publie
pas : les executions continuent de tourner l'ancienne version tant qu'on n'a pas publie.

Apres tout `update_workflow`, publier la nouvelle version :

```text
publish_workflow(workflowId)   # MCP n8n
```

Symptome typique si on oublie : le workflow "s'arrete au debut" / ne reflete pas les derniers
changements alors que l'editeur montre le nouveau graphe.

## Redemarrage complet

```bash
cd /SSD/n8n
docker compose up -d
sudo systemctl restart memo-bridge.service
```

Installation du bridge et du watchdog :

```bash
sudo install -d -o debian -g debian -m 700 /SSD/n8n/runtime
sudo install -m 644 systemd/memo-bridge.service /etc/systemd/system/
sudo install -m 644 systemd/n8n-monitor.service systemd/n8n-monitor.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now memo-bridge.service n8n-monitor.timer
```

## Partage des pages Notion avec l'integration n8n

Le workflow Daily Brief accede a plusieurs pages Notion. Chaque page doit etre partagee manuellement avec l'integration **n8n RPi** (page Notion → `...` → Connexions → ajouter n8n RPi) :

| Ressource | Variable | Objet |
|------|----|-------|
| Daily Brief | `NOTION_DAILY_BRIEF_PAGE_ID` | destination du brief |
| Notes | `NOTION_NOTES_PAGE_ID` | journal récent |
| Objectifs | `NOTION_OBJECTIVES_DATABASE_ID` | objectifs actifs |
| Tâches | `NOTION_TASKS_DATABASE_ID` | suivi et création des tâches |
| Contexte Système | `NOTION_CONTEXT_PAGE_ID` | contexte, priorités et règles |
| Inbox IA | `NOTION_INBOX_DATABASE_ID` | captures manuelles et automatiques |

Attention : les DB Objectifs et Tâches ont ete creees via le connecteur MCP Notion (une integration
differente de "n8n RPi"). Elles doivent donc etre partagees explicitement avec n8n RPi, sinon les
nœuds Notion renvoient 404.

La page `Contexte Système`, configurée par `NOTION_CONTEXT_PAGE_ID`, est l'unique source du profil.
Les données sont réparties en trois couches réellement utilisées au runtime :
- identité, situation, projets, priorités, contraintes et règles → page `Contexte Système` ;
- objectifs → DB 🎯 Objectifs (source dynamique : editer la DB, pas le Profil) ;
- journal → page Notes.

Modifier `Contexte Système` dès qu'un fait structurant ou une règle change. Si sa lecture échoue, le
bridge refuse la génération contextuelle, n'injecte aucun profil statique et déclenche une alerte.

## Bridge memo-bridge.py — moteur de génération

Le bridge `/brief` utilise une **chaîne de fallback** pour générer le brief :

1. **Claude** (`claude-sonnet-4-6`, `claude -p --strict-mcp-config`) — moteur principal.
2. **Codex** (`codex exec --sandbox read-only --skip-git-repo-check`) — fallback si Claude échoue
   (quota épuisé, binaire absent, timeout). Utilise la clé OpenAI API configurée dans
   `~/.codex/config.toml`. Aucun abonnement ChatGPT Plus requis — facturation à l'usage API.
3. **none** — si les deux échouent, le bridge renvoie 502 et n8n active le fallback JS interne.

La fonction `run_brief_engine(prompt, model)` dans `memo-bridge.py` encapsule cette logique et
retourne `(text, engine)` où `engine` vaut `"claude"`, `"codex"` ou `"none"`.

La réponse `/brief` inclut `engine` et `context_source` :
`{brief, blocks, tasks, count, engine, context_source}`.

Règle de sécurité : `--strict-mcp-config` est **obligatoire** sur `claude -p`. Cela désactive tous
les serveurs MCP (zéro contexte externe), faisant de Claude un pur résumeur qui ne peut ni lire ni
écrire rien en dehors du prompt. Ne jamais retirer ce flag.

## Observabilité Telegram

Branche de monitoring dans le workflow Daily Brief :

- **Détecter dégradation** (Code) : alerte si `engine !== "claude"` ou si
  `context_source !== "notion"`.
- **Alerte Telegram** : utilise `TELEGRAM_BOT_TOKEN` et `TELEGRAM_CHAT_ID` depuis `.env`.

Message envoyé :
```
⚠️ Daily Brief — moteur dégradé
Moteur utilisé : codex   ← ou "none"
Date : JJ/MM/AAAA
Claude n'était pas disponible. Le brief a tourné en fallback (Codex).
```

En usage normal (Claude disponible), cette branche ne s'exécute pas et n'envoie rien.

## Prompt Daily Brief

Le bridge `POST /brief` genere le brief via `claude-sonnet-4-6` (ou Codex en fallback). C'est un
**copilote oriente objectifs** : il part des objectifs, les captures et le journal sont du carburant.
Entrees du prompt :

- **system_context** : blocs de la page Notion `Contexte Système`, y compris les règles du copilote.
- **objectives** : DB Objectifs (filtre Statut=Actif), lu par `Enrichir payload`.
- **open_tasks** : DB Tâches (filtre Statut=À faire) → suivi des tâches des jours precedents.
- **completed_tasks** : tâches passées à `Fait` dans les trois derniers jours, triées de la plus
  récente à la plus ancienne (10 maximum). `Faite le` est utilisée si elle est renseignée, sinon la
  date de dernière modification Notion. La propriété texte `Retour` permet d'indiquer le résultat
  obtenu ou le blocage rencontré et est transmise à Claude.
- **items** : captures Inbox IA du jour.
- **context** : journal recent (section `📓 Journal` de Notes).

Sortie : `{brief (markdown), blocks (Notion), tasks[], count, engine}`. `extract_tasks()` parse la
section ✅ Tâches du jour (format `- **[Domaine]** Titre — pourquoi`) ; n8n cree ces tâches dans la DB.

Structure du brief produit (~400 mots max) :

```
## 🗓️ Daily Brief — JJ/MM/AAAA
### 📌 Suivi                      ← progrès récents + tâches ouvertes
### 🔗 Connexions
### ⚡ Contradictions / angles morts
### ✅ Tâches du jour             ← 1-3 tâches, parsees vers la DB Tâches
### 🎓 À apprendre
### ❓ Question à explorer
```

## Points de vigilance

- `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` est necessaire parce que les workflows lisent `$env.MEMO_TOKEN` et `$env.CAPTURE_TOKEN`.
- `--strict-mcp-config` sur `claude -p` est obligatoire : zero MCP servers, Claude = pure summarizer.
- `Daily Brief` a deux niveaux de fallback : d'abord Codex (dans le bridge), puis brief JS minimaliste (dans n8n). Une alerte Telegram signale toute dégradation.
- `Capture -> Notion` depend du bridge `/summarize`, mais le bridge possede lui-meme un fallback pour sauvegarder une capture meme si Claude ne repond pas.
- `/summarize` essaie Claude Haiku, puis Codex. Son champ `engine` indique `claude`, `codex` ou
  `none`; dans ce dernier cas seulement, la capture locale minimale est utilisée.
- Les backups locaux peuvent contenir d'anciens secrets. Ils sont ignores par Git, mais doivent etre purges si une rotation stricte est necessaire.
- Le workflow Daily Brief est **actif**. Il tourne tous les jours a 7h, meme sans nouvelle capture (pilote par les objectifs).
- Toutes les pages et bases Notion doivent être partagées avec l'intégration choisie par l'opérateur.

## Observabilité globale

- Le workflow `Monitoring — erreurs globales` reçoit les erreurs des workflows critiques et envoie
  le workflow, le nœud, le message et l'exécution à Telegram.
- Les lectures Notion auparavant tolérées sont vérifiées explicitement : une indisponibilité devient
  une erreur observable au lieu de produire silencieusement un résultat vide.
- Après une capture et après l'écriture du Daily Brief, n8n appelle les routes heartbeat du bridge.
- Le timer systemd `n8n-monitor.timer` vérifie toutes les cinq minutes n8n (healthcheck),
  cloudflared, memo-bridge et la présence du heartbeat quotidien après `BRIEF_EXPECTED_BY`.
- Les alertes du watchdog sont envoyées lors d'une transition vers l'échec et lors du rétablissement,
  afin d'éviter une notification identique toutes les cinq minutes.

## Reproductibilité et garde-fous

Les images n8n et cloudflared sont épinglées par version et digest. CPU et mémoire ne sont pas
plafonnés. Le compose limite seulement le nombre de processus et fait tourner les logs Docker pour
éviter une saturation du système ou du disque.
