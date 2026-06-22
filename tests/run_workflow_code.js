const fs = require('fs');

const request = JSON.parse(fs.readFileSync(0, 'utf8'));
const workflows = JSON.parse(fs.readFileSync(request.workflow, 'utf8'));
const workflow = workflows[0];
const node = workflow.nodes.find(candidate => candidate.name === request.node);
if (!node || !node.parameters || typeof node.parameters.jsCode !== 'string') {
  throw new Error(`Code node not found: ${request.node}`);
}

const asItems = values => (values || []).map(value => (
  value && Object.prototype.hasOwnProperty.call(value, 'json') ? value : { json: value }
));
const inputItems = asItems(request.input);
const nodeOutputs = Object.fromEntries(
  Object.entries(request.nodes || {}).map(([name, values]) => [name, asItems(values)]),
);
const accessor = name => {
  const items = nodeOutputs[name] || [];
  return {
    all: () => items,
    first: () => items[0] || { json: {} },
    item: items[0] || { json: {} },
  };
};
const $input = {
  all: () => inputItems,
  first: () => inputItems[0] || { json: {} },
};
const $env = request.env || {};

const execute = new Function(
  '$input',
  '$',
  '$now',
  '$env',
  `"use strict"; return (function () {\n${node.parameters.jsCode}\n})();`,
);

Promise.resolve(execute($input, accessor, request.now || new Date().toISOString(), $env))
  .then(result => process.stdout.write(JSON.stringify(result === undefined ? null : result)))
  .catch(error => {
    process.stderr.write(`${error.stack || error}\n`);
    process.exitCode = 1;
  });
