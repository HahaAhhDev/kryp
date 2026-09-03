#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <stdarg.h>
#include <Python.h>

#define MAX_SRC (1024 * 1024)
#define VERSION "0.1.0"

static const char *KRYP_RUNTIME =
    "def __kryp_console_error__(msg):\n"
    "    import sys\n"
    "    print(f'\\033[91m{msg}\\033[0m', file=sys.stderr)\n"
    "\n"
    "def __kryp_exec_js__(code):\n"
    "    import subprocess\n"
    "    r = subprocess.run(['node','-e',code], capture_output=True, text=True)\n"
    "    if r.stdout: print(r.stdout, end='')\n"
    "    if r.stderr: print(r.stderr, end='', file=sys.stderr)\n"
    "\n"
    "def __kryp_exec_sh__(code):\n"
    "    import subprocess\n"
    "    r = subprocess.run(code, shell=True, capture_output=True, text=True)\n"
    "    if r.stdout: print(r.stdout, end='')\n"
    "    if r.stderr: print(r.stderr, end='', file=sys.stderr)\n";

/* ── Buffer ──────────────────────────────────────────────── */
typedef struct { char *buf; size_t len; size_t cap; } Buffer;

static void buf_init(Buffer *b) {
    b->cap = 8192; b->buf = malloc(b->cap); b->len = 0;
}
static void buf_append(Buffer *b, const char *s, size_t n) {
    while (b->len + n >= b->cap) { b->cap *= 2; b->buf = realloc(b->buf, b->cap); }
    memcpy(b->buf + b->len, s, n); b->len += n;
}
static void buf_str(Buffer *b, const char *s) { buf_append(b, s, strlen(s)); }
static void buf_char(Buffer *b, char c) { buf_append(b, &c, 1); }

/* ── Lexer helpers ───────────────────────────────────────── */
static int skip_ws(const char *s, int i) {
    while (s[i] == ' ' || s[i] == '\t') i++;
    return i;
}

static int read_ident(const char *s, int i, char *out, int max) {
    int start = i;
    while (isalnum((unsigned char)s[i]) || s[i] == '_') i++;
    int len = i - start;
    if (len >= max) len = max - 1;
    memcpy(out, s + start, len);
    out[len] = '\0';
    return i;
}

/* Convert var:{name} → {name} for Python f-strings */
static void emit_interp_string(Buffer *out, const char *s, int start, int end) {
    buf_str(out, "f\"");
    for (int i = start; i < end; i++) {
        if (i + 5 <= end && strncmp(s + i, "var:{", 5) == 0) {
            i += 5;
            buf_char(out, '{');
            while (i < end && s[i] != '}') { buf_char(out, s[i]); i++; }
            buf_char(out, '}');
        } else if (s[i] == '"' || s[i] == '\\') {
            buf_char(out, '\\');
            buf_char(out, s[i]);
        } else {
            buf_char(out, s[i]);
        }
    }
    buf_char(out, '"');
}

/* ── Transpiler ──────────────────────────────────────────── */
static char *transpile(const char *source) {
    Buffer out;
    buf_init(&out);
    int len = strlen(source);
    int i = 0;
    int at_line_start = 1;

    while (i < len) {
        /* Skip \r */
        if (source[i] == '\r') { i++; continue; }

        /* Newline */
        if (source[i] == '\n') {
            buf_char(&out, '\n');
            i++;
            at_line_start = 1;
            continue;
        }

        /* Indentation at line start */
        if (at_line_start) {
            int spaces = 0;
            while (i < len && source[i] == ' ') { spaces++; i++; }
            while (i < len && source[i] == '\t') { spaces += 4; i++; }
            int indent = spaces / 4;
            for (int s = 0; s < indent; s++) buf_str(&out, "    ");
            at_line_start = 0;
            if (i >= len || source[i] == '\n') continue;
        }

        /* Comments: -- ... */
        if (source[i] == '-' && i + 1 < len && source[i + 1] == '-') {
            buf_str(&out, "# ");
            i += 2;
            while (i < len && source[i] != '\n') { buf_char(&out, source[i]); i++; }
            continue;
        }

        /* String literals with var:{} interpolation */
        if (source[i] == '"') {
            i++;
            int ss = i;
            while (i < len && source[i] != '"') {
                if (source[i] == '\\' && i + 1 < len) i++;
                i++;
            }
            emit_interp_string(&out, source, ss, i);
            if (i < len) i++; /* skip closing quote */
            continue;
        }

        /* => operator → : */
        if (source[i] == '=' && i + 1 < len && source[i + 1] == '>') {
            buf_char(&out, ':');
            i += 2;
            /* Single-line body: add space if next non-ws char isn't newline */
            int j = skip_ws(source, i);
            if (j < len && source[j] != '\n' && source[j] != '\0') {
                buf_char(&out, ' ');
            }
            continue;
        }

        /* Operators */
        if (source[i] == '&' && i + 1 < len && source[i + 1] == '&') {
            buf_str(&out, " and "); i += 2; continue;
        }
        if (source[i] == '|' && i + 1 < len && source[i + 1] == '|') {
            buf_str(&out, " or "); i += 2; continue;
        }

        /* Keywords */
        if (isalpha((unsigned char)source[i]) || source[i] == '_') {
            char word[64];
            int wi = read_ident(source, i, word, sizeof(word));
            int wlen = wi - i;

            /* fn → def */
            if (wlen == 2 && memcmp(word, "fn", 2) == 0) {
                buf_str(&out, "def "); i = wi; continue;
            }

            /* var → skip keyword + trailing space */
            if (wlen == 3 && memcmp(word, "var", 3) == 0) {
                i = wi;
                if (i < len && source[i] == ' ') i++;
                continue;
            }

            /* if → if (with trailing space) */
            if (wlen == 2 && memcmp(word, "if", 2) == 0) {
                buf_str(&out, "if "); i = wi; continue;
            }

            /* else if → elif | else → else */
            if (wlen == 4 && memcmp(word, "else", 4) == 0) {
                i = wi;
                int j = skip_ws(source, i);
                if (j + 1 < len && source[j] == 'i' && source[j + 1] == 'f'
                    && !isalnum((unsigned char)source[j + 2])) {
                    buf_str(&out, "elif ");
                    i = j + 2;
                    if (i < len && source[i] == ' ') i++;
                } else {
                    buf_str(&out, "else");
                }
                continue;
            }

            /* for → for (with trailing space) */
            if (wlen == 3 && memcmp(word, "for", 3) == 0) {
                buf_str(&out, "for "); i = wi; continue;
            }

            /* while → while (with trailing space) */
            if (wlen == 5 && memcmp(word, "while", 5) == 0) {
                buf_str(&out, "while "); i = wi; continue;
            }

            /* in → surrounded by spaces */
            if (wlen == 2 && memcmp(word, "in", 2) == 0) {
                buf_str(&out, " in "); i = wi; continue;
            }

            /* true/false/none → True/False/None */
            if (wlen == 4 && memcmp(word, "true", 4) == 0) {
                buf_str(&out, "True"); i = wi; continue;
            }
            if (wlen == 5 && memcmp(word, "false", 5) == 0) {
                buf_str(&out, "False"); i = wi; continue;
            }
            if (wlen == 4 && memcmp(word, "none", 4) == 0) {
                buf_str(&out, "None"); i = wi; continue;
            }

            /* pyimport → import */
            if (wlen == 8 && memcmp(word, "pyimport", 8) == 0) {
                buf_str(&out, "import ");
                i = wi;
                if (i < len && source[i] == ' ') i++;
                continue;
            }

            /* console.method → print / __kryp_console_error__ */
            if (wlen == 7 && memcmp(word, "console", 7) == 0) {
                i = wi;
                if (i < len && source[i] == '.') {
                    i++;
                    char method[32];
                    int mi = read_ident(source, i, method, sizeof(method));
                    if (strcmp(method, "log") == 0)       buf_str(&out, "print");
                    else if (strcmp(method, "error") == 0) buf_str(&out, "__kryp_console_error__");
                    else if (strcmp(method, "warn") == 0)  buf_str(&out, "__kryp_console_error__");
                    else if (strcmp(method, "debug") == 0) buf_str(&out, "print");
                    else                                   buf_str(&out, "print");
                    i = mi;
                } else {
                    buf_str(&out, "print");
                }
                continue;
            }

            /* exec(var:lang, "code") or exec("code") */
            if (wlen == 4 && memcmp(word, "exec", 4) == 0) {
                i = wi;
                if (i < len && source[i] == '(') {
                    i++; /* skip ( */
                    i = skip_ws(source, i);
                    /* Check for var:lang */
                    if (i + 3 < len && strncmp(source + i, "var:", 4) == 0) {
                        i += 4;
                        char lang[16];
                        int li = read_ident(source, i, lang, sizeof(lang));
                        i = skip_ws(source, li);
                        if (i < len && source[i] == ',') i++;
                        i = skip_ws(source, i);
                        /* Read code string */
                        if (i < len && source[i] == '"') {
                            i++; /* skip opening quote */
                            int cs = i;
                            while (i < len && source[i] != '"') {
                                if (source[i] == '\\' && i + 1 < len) i++;
                                i++;
                            }
                            /* Emit appropriate call */
                            if (strcmp(lang, "python") == 0) {
                                buf_str(&out, "exec(");
                                emit_interp_string(&out, source, cs, i);
                                buf_str(&out, ")");
                            } else if (strcmp(lang, "js") == 0) {
                                buf_str(&out, "__kryp_exec_js__(");
                                emit_interp_string(&out, source, cs, i);
                                buf_str(&out, ")");
                            } else if (strcmp(lang, "sh") == 0) {
                                buf_str(&out, "__kryp_exec_sh__(");
                                emit_interp_string(&out, source, cs, i);
                                buf_str(&out, ")");
                            } else {
                                buf_str(&out, "exec(");
                                emit_interp_string(&out, source, cs, i);
                                buf_str(&out, ")");
                            }
                            if (i < len) i++; /* skip closing quote */
                            /* Skip to closing paren */
                            while (i < len && source[i] != ')') i++;
                            if (i < len) i++; /* skip ) */
                        }
                    } else {
                        /* No var:lang → default exec */
                        buf_str(&out, "exec(");
                        int depth = 1;
                        while (i < len && depth > 0) {
                            if (source[i] == '(') depth++;
                            else if (source[i] == ')') depth--;
                            if (depth > 0) buf_char(&out, source[i]);
                            i++;
                        }
                        buf_char(&out, ')');
                    }
                }
                continue;
            }

            /* Unknown identifier → pass through */
            buf_append(&out, word, wlen);
            i = wi;
            continue;
        }

        /* Everything else passes through */
        buf_char(&out, source[i]);
        i++;
    }

    buf_char(&out, '\0');
    return out.buf;
}

/* ── File I/O ────────────────────────────────────────────── */
static char *read_file(const char *path) {
    FILE *f = fopen(path, "r");
    if (!f) { fprintf(stderr, "✗ Cannot open %s\n", path); return NULL; }
    fseek(f, 0, SEEK_END);
    long sz = ftell(f);
    rewind(f);
    if (sz > MAX_SRC) { fprintf(stderr, "✗ File too large (>1MB)\n"); fclose(f); return NULL; }
    char *buf = malloc(sz + 1);
    if (!buf) { fclose(f); return NULL; }
    fread(buf, 1, sz, f);
    buf[sz] = '\0';
    fclose(f);
    return buf;
}

static void py_exec(const char *code) {
    if (PyRun_SimpleString(code) != 0) {
        PyErr_Print();
        fprintf(stderr, "✗ Execution failed\n");
    }
}

/* ── Commands ────────────────────────────────────────────── */
static int cmd_run(const char *path) {
    const char *ext = strrchr(path, '.');
    if (ext && strcmp(ext, ".kryc") == 0) {
        char *data = read_file(path);
        if (!data) return 1;
        char *script;
        asprintf(&script, "import base64\nexec(base64.b64decode('''%s''').decode())\n", data);
        free(data);
        py_exec(script);
        free(script);
    } else {
        char *src = read_file(path);
        if (!src) return 1;
        char *py = transpile(src);
        free(src);
        if (!py) return 1;
        py_exec(py);
        free(py);
    }
    return 0;
}

static int cmd_compile(const char *path) {
    char *src = read_file(path);
    if (!src) return 1;
    char *py = transpile(src);
    free(src);
    if (!py) return 1;
    char *out;
    asprintf(&out, "%s.kryc", path);
    char *script;
    asprintf(&script,
        "import base64\n"
        "with open('%s','w') as f:\n"
        "    f.write(base64.b64encode(b'''%s''').decode())\n",
        out, py);
    py_exec(script);
    printf("✓ Compiled to %s\n", out);
    free(py); free(out); free(script);
    return 0;
}

static int cmd_install(const char *pkg) {
    char *cmd;
    asprintf(&cmd, "pip install %s", pkg);
    printf("Installing %s...\n", pkg);
    int rc = system(cmd);
    free(cmd);
    if (rc == 0) printf("✓ Installed %s\n", pkg);
    else fprintf(stderr, "✗ Failed to install %s\n", pkg);
    return rc;
}

static void usage(void) {
    printf("Kryp v%s\n"
           "Usage:\n"
           "  kryp run <file.kryp|file.kryc>\n"
           "  kryp compile <file.kryp>\n"
           "  kryp install <package>\n", VERSION);
}

/* ── Main ────────────────────────────────────────────────── */
int main(int argc, char **argv) {
    if (argc < 2) { usage(); return 1; }
    Py_Initialize();
    PyRun_SimpleString(KRYP_RUNTIME);

    int rc = 0;
    if      (strcmp(argv[1], "run")     == 0 && argc >= 3) rc = cmd_run(argv[2]);
    else if (strcmp(argv[1], "compile") == 0 && argc >= 3) rc = cmd_compile(argv[2]);
    else if (strcmp(argv[1], "install") == 0 && argc >= 3) rc = cmd_install(argv[2]);
    else { usage(); rc = 1; }

    Py_Finalize();
    return rc;
}