import { createConnection, TextDocuments, Diagnostic, DiagnosticSeverity, ProposedFeatures, InitializeParams, TextDocumentSyncKind, CompletionItem, CompletionItemKind, MarkupKind } from 'vscode-languageserver/node';
import { TextDocument } from 'vscode-languageserver-textdocument';

const connection = createConnection(ProposedFeatures.all);
const documents = new TextDocuments(TextDocument);

connection.onInitialize((_params: InitializeParams) => ({
    capabilities: {
        textDocumentSync: TextDocumentSyncKind.Incremental,
        completionProvider: { triggerCharacters: ['.', ':'] },
        hoverProvider: true
    }
}));

documents.onDidChangeContent(change => validateDocument(change.document));

function validateDocument(doc: TextDocument) {
    const diagnostics: Diagnostic[] = [];
    const lines = doc.getText().split('\n');

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const openMatches = line.match(/var:\{/g);
        const closeMatches = line.match(/\}/g);
        if (openMatches && (!closeMatches || openMatches.length > closeMatches.length)) {
            diagnostics.push({
                severity: DiagnosticSeverity.Error,
                range: { start: { line: i, character: line.indexOf('var:{') }, end: { line: i, character: line.length } },
                message: 'Unclosed var:{} interpolation',
                source: 'kryp'
            });
        }
        const execMatch = line.match(/\bexec\s*\(\s*"(?!var:)/);
        if (execMatch) {
            diagnostics.push({
                severity: DiagnosticSeverity.Warning,
                range: { start: { line: i, character: execMatch.index! }, end: { line: i, character: execMatch.index! + 6 } },
                message: 'Consider using exec(var:python, ...) for explicit language targeting',
                source: 'kryp'
            });
        }
    }
    connection.sendDiagnostics({ uri: doc.uri, diagnostics });
}

connection.onCompletion(() => {
    const keywords = ['fn', 'var', 'if', 'else', 'for', 'while', 'in', 'pyimport', 'exec', 'console', 'true', 'false', 'none'];
    const consoleMethods = ['log', 'error', 'warn', 'debug'];
    const execLangs = ['python', 'js', 'sh', 'raw'];

    const items: CompletionItem[] = [
        ...keywords.map(k => ({ label: k, kind: CompletionItemKind.Keyword })),
        ...consoleMethods.map(m => ({ label: `console.${m}`, kind: CompletionItemKind.Method })),
        ...execLangs.map(l => ({ label: `var:${l}`, kind: CompletionItemKind.Constant }))
    ];
    return items;
});

connection.onHover(params => {
    const doc = documents.get(params.textDocument.uri);
    if (!doc) return null;
    const line = doc.getText({ start: { line: params.position.line, character: 0 }, end: { line: params.position.line, character: 999 } });
    const pos = params.position.character;
    let start = pos, end = pos;
    while (start > 0 && /[a-zA-Z_:]/.test(line[start - 1])) start--;
    while (end < line.length && /[a-zA-Z0-9_]/.test(line[end])) end++;
    const word = line.substring(start, end);

    const docs: Record<string, string> = {
        'fn': 'Define a function: `fn name(args) => body`',
        'var': 'Declare a variable: `var x = value`',
        '=>': 'Block introducer. Requires newline+indent or single expression.',
        'var:{}': 'String interpolation: `"Hello var:{name}"`',
        'exec': 'Execute code: `exec(var:python, "code")` or `exec("kryp code")`',
        'pyimport': 'Import Python module: `pyimport os` or `pyimport json as j`',
        'console.log': 'Print to stdout',
        'console.error': 'Print red error to stderr'
    };
    if (docs[word]) return { contents: { kind: MarkupKind.Markdown, value: docs[word] } };
    return null;
});

documents.listen(connection);
connection.listen();