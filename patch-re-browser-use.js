import { Project, Node, SyntaxKind, IndentationText } from 'ts-morph';
import path from 'path';
const FILES_LOCATION_PREFIX = "browser-use/"
const filePath = path.resolve(`${FILES_LOCATION_PREFIX}browser_use/dom/buildDomTree.js`);

// Initialize a ts-morph project. It's configured to handle JavaScript files.
const project = new Project({
  manipulationSettings: {
    indentationText: IndentationText.TwoSpaces,
  }
});

// Add the source file to the project, which reads and parses it.
const sourceFile = project.addSourceFileAtPath(filePath);

let arrowFunc = null;
// Find the first arrow function inside the first expression statement.
const expressionStatement = sourceFile.getFirstDescendantByKind(SyntaxKind.ExpressionStatement);
arrowFunc = expressionStatement.getFirstDescendantByKind(SyntaxKind.ArrowFunction);
// Get the function body to modify its contents.
const funcBody = arrowFunc.getBody();

// --- 1. Add new default parameters to the function's argument object ---
const argsParam = arrowFunc.getParameter('args'); // Find parameter by name
if (argsParam) {
  const defaultParamsObject = argsParam.getInitializerIfKind(SyntaxKind.ObjectLiteralExpression);
  if (defaultParamsObject) {
    if (!defaultParamsObject.getProperty('initialRootNode')) {
      defaultParamsObject.addPropertyAssignment({ name: 'initialRootNode', initializer: 'null' });
    }
    if (!defaultParamsObject.getProperty('highlightIndex')) {
      defaultParamsObject.addPropertyAssignment({ name: 'highlightIndex', initializer: '0' });
    }
  }
}

// --- 2. Update destructuring to include initialRootNode ---
const argsDestructuringStatement = funcBody.getVariableStatement(stmt => {
  const decl = stmt.getDeclarations()[0];
  return decl && decl.getInitializer()?.getText() === 'args';
});

const declaration = argsDestructuringStatement.getDeclarations()[0];
const nameNode = declaration.getNameNode();
const text = nameNode.getText();

// Only add if not already present
if (!/\binitialRootNode\b/.test(text)) {
  // Insert before the closing }
  const newText = text.replace(/}\s*$/, ', initialRootNode }');
  nameNode.replaceWithText(newText);
}

// --- 3. Update highlightIndex initialization and remove comment ---
const highlightIndexDeclaration = funcBody.getVariableDeclaration('highlightIndex');
const varStatement = highlightIndexDeclaration.getParent().getParent();
if (Node.isVariableStatement(varStatement)) {
    // Remove the old statement (and its comments)
    const statements = funcBody.getStatements();
    const index = statements.indexOf(varStatement);
    varStatement.remove();
    // Insert the new statement where the old one was ...
    funcBody.insertStatements(index, 'let highlightIndex = args.highlightIndex || 0;\n');
}

/* --- 4. Adding the child to document.body doesn't work when that document.body is the host of a ShadowRoot. 
          In that case you need to invoke appendChild directly in the shadowRoot */
const highlightElementFuncBody = funcBody.getFunctions().find(fn => fn.getName() === "highlightElement").getBodyOrThrow();
highlightElementFuncBody.forEachDescendant((node) => {
  if (
    node.getKind() === SyntaxKind.ExpressionStatement &&
    node.getText().trim() === "document.body.appendChild(container);"
  ) {
    node.replaceWithText(
      `const rootNode = element?.getRootNode();
if (rootNode?.host === document.body)
  rootNode.appendChild(container);
else
  document.body.appendChild(container);`
    );
  }
})

/* --- 5. We need to deal as well with ShadowRoot nodes whose node.nodeType === Node.DOCUMENT_FRAGMENT_NODE ...*/
const buildDomTreeFuncBody = funcBody.getFunctions().find(fn => fn.getName() === "buildDomTree").getBodyOrThrow();
let ifStatement = buildDomTreeFuncBody
  .getDescendantsOfKind(SyntaxKind.IfStatement)
  .find(ifStmt =>
    ifStmt.getExpression().getText().includes("!node || node.id === HIGHLIGHT_CONTAINER_ID") &&
    ifStmt.getExpression().getText().includes("node.nodeType !== Node.ELEMENT_NODE && node.nodeType !== Node.TEXT_NODE")
  );

const expr = ifStatement.getExpression();
// Find the specific BinaryExpression node
const targetBinaryExpr = expr.getDescendantsOfKind(SyntaxKind.BinaryExpression)
  .find(binExpr => binExpr.getText() === "node.nodeType !== Node.TEXT_NODE");

// Replace only the sub-expression, not the whole condition to preserve formatting ...
targetBinaryExpr.replaceWithText(
  "node.nodeType !== Node.TEXT_NODE && node.nodeType !== Node.DOCUMENT_FRAGMENT_NODE"
);

/* --- 6. I don't think it's a good idea to treat 'body' in a different way instead of using getXPathTree(node, true) ... */
// Find the if statement for "if (node === document.body)"
ifStatement = buildDomTreeFuncBody.getDescendantsOfKind(SyntaxKind.IfStatement).find(ifStmt =>
  ifStmt.getExpression().getText() === "node === document.body"
);

// Find the nodeData variable declaration in the if block
const nodeDataDecl = ifStatement.getThenStatement().getDescendantsOfKind(SyntaxKind.VariableDeclaration).find(decl =>
  decl.getName() === "nodeData"
);

// Replace the initializer with the new object literal
const objLiteral = nodeDataDecl.getInitializerIfKindOrThrow(SyntaxKind.ObjectLiteralExpression);
objLiteral.replaceWithText(writer => {
  writer.writeLine("{");
  writer.writeLine(`  tagName: 'body',`);
  writer.writeLine(`  attributes: {},`);
  writer.writeLine(`  xpath: getXPathTree(node, true),`);
  writer.writeLine(`  children: [],`);
  writer.write("}");
});

/* --- 7. Special handling when the root node is a ShadowRoot which will be the necessary case when dealing with mode = 'closed' */
const parentBlock = ifStatement.getParentIfKindOrThrow(SyntaxKind.Block);
const index = ifStatement.getChildIndex();
parentBlock.insertStatements(index + 1, `
if (node instanceof ShadowRoot) {
  // Using values from host ...
  const host = node?.host;
  const nodeData = {
    tagName: host.tagName.toLowerCase(),
    attributes: {},
    xpath: getXPathTree(host, true),
    children: [],
    shadowRoot: true
  };

  // Process children of ShadowRoot, nothing special about them
  for (const child of node.childNodes) {
    const domElement = buildDomTree(child, parentIframe);
    if (domElement) nodeData.children.push(domElement);
  }

  const id = \`\${ID.current++}\`;
  DOM_HASH_MAP[id] = nodeData;
  if (debugMode) PERF_METRICS.nodeMetrics.processedNodes++;
  return id;
}`);

/* --- 8. We are not always use 'body' as the 'initialRootNode' ... */
const rootIdDecl = funcBody.getDescendantsOfKind(SyntaxKind.VariableDeclaration)
  .find(decl => decl.getName() === "rootId" && decl.getInitializerOrThrow().getText() === "buildDomTree(document.body)");

const rootIdStatement = rootIdDecl.getFirstAncestorByKindOrThrow(SyntaxKind.VariableStatement);
rootIdStatement.replaceWithText([
  "const rootNodeToProcess = initialRootNode || document.body;",
  "const rootId = buildDomTree(rootNodeToProcess);"
].join("\n"));

// Save the modified file back to disk.
sourceFile.saveSync();

console.log(`Successfully updated ${filePath} using ts-morph.`);
