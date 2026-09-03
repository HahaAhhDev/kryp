#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <unistd.h>
#include <sys/wait.h>
#include <Python.h>

#define MAX_SRC (1024 * 1024)
#define MAX_OUT (MAX_SRC * 4)
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

/* ── Helpers ─────────────────────────────────────────────── */
static char *read_file(const char *path) {
    FILE *f = fopen(path, "r");
    if (!f) { fprintf(stderr, "✗ Cannot open %s\n", path); return NULL; }
    fseek(f, 0, SEEK_END);
    long len = ftell(f);
    if (len > MAX_SRC) { fprintf(stderr, "✗ File too large\n"); fclose(f); return NULL; }
    rewind(f);
    char *buf = malloc(len + 1);
    if (!buf) { fclose(f); return NULL; }
    fread(buf, 1, len, f);
    buf[len] = '\0';
    fclose(f);
    return buf;
}

static void py_exec(const char *code) {
    if (PyRun_SimpleString(code) != 0) {
        PyErr_Print();
        fprintf(stderr, "✗ Execution failed\n");
    }
}

/* ── Transpiler ──────────────────────────────────────────── */
typedef struct {
    char *buf;
    size_t len;
    size_t cap;
} Buffer;

static void buf_init(Buffer *b) {
    b->cap = 4096;
    b->buf = malloc(b->cap);
    b->len = 0;
}

static void buf_append(Buffer *b, const char *s, size_t n) {
    while (b->len + n >= b->cap) {
        b->cap *= 2;
        b->buf = realloc(b->buf, b->cap);
    }
    memcpy(b->buf + b->len, s, n);
    b->len += n;
}

static void buf_str(Buffer *b, const char *s) { buf_append(b, s, strlen(s)); }
static void buf_char(Buffer *b, char c) { buf_append(b, &c, 1); }

static void buf_printf(Buffer *b, const char *fmt, ...) {
    char tmp[1024];
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(tmp, sizeof(tmp), fmt, ap);
    va_end(ap);
    if (n > 0) buf_append(b, tmp, n);
}

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
        if (i + 5 < end && strncmp(s + i, "var:{", 5) == 0) {
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

static char *transpile(const char *source) {
    Buffer out;
    buf_init(&out);

    int indent = 0;
    int len = strlen(source);
    int i = 0;

    while (i < len) {
        /* Skip \r */
        if (source[i] == '\r') { i++; continue; }

        /* Newline */
        if (source[i] == '\n') {
            buf_char(&out, '\n');
            i++;
            continue;
        }

        /* Comments: -- ... */
        if (source[i] == '-' && source[i+1] == '-') {
            buf_str(&out, "# ");
            i += 2;
            while (i < len && source[i] != '\n') { buf_char(&out, source[i]); i++; }
            continue;
        }

        /* Indentation tracking for => blocks */
        int line_start = (i == 0 || source[i-1] == '\n');
        if (line_start) {
            int spaces = 0;
            while (i < len && source[i] == ' ') { spaces++; i++; }
            while (i < len && source[i] == '\t') { spaces += 4; i++; }
            indent = spaces / 4;
            for (int s = 0; s < indent; s++) buf_str(&out, "    ");
            if (i >= len || source[i] == '\n') continue;
        }

        /* String literals with var:{} interpolation */
        if (source[i] == '"') {
            i++; /* skip opening quote */
            int str_start = i;
            while (i < len && source[i] != '"') {
                if (source[i] == '\\' && i+1 < len) i++;
                i++;
            }
            emit_interp_string(&out, source, str_start, i);
            if (i < len) i++; /* skip closing quote */
            continue;
        }

        /* Keywords */
        if (isalpha((unsigned char)source[i]) || source[i] == '_') {
            char word[64];
            int wi = read_ident(source, i, word, sizeof(word));
            int wlen = wi - i;

            if (strncmp(word, "fn", wlen) == 0 && wlen == 2) {
                buf_str(&out, "def ");
                i = wi;
                continue;
            }
            if (strncmp(word, "var", wlen) == 0 && wlen == 3) {
                /* Check if var:lang pattern for exec */
                if (wi < len && source[wi] == ':') {
                    /* var: something — could be exec lang tag or just var decl */
                    /* Peek ahead: if preceded by exec( it's a lang tag, else it's decl */
                    /* For simplicity, treat standalone "var" as declaration */
                    buf_str(&out, ""); /* skip 'var', Python doesn't need it */
                    i = wi;
                    continue;
                }
                buf_str(&out, ""); /* var keyword → nothing in Python */
                i = wi;
                continue;
            }
            if (strncmp(word, "console", wlen) == 0 && wlen == 7) {
                /* console.log → print, console.error → __kryp_console_error__ */
                i = wi;
                if (i < len && source[i] == '.') {
                    i++; /* skip dot */
                    char method[32];
                    int mi = read_ident(source, i, method, sizeof(method));
                    if (strcmp(method, "log") == 0) {
                        buf_str(&out, "print");
                    } else if (strcmp(method, "error") == 0) {
                        buf_str(&out, "__kryp_console_error__");
                    } else if (strcmp(method, "warn") == 0) {
                        buf_str(&out, "__kryp_console_error__");
                    } else {
                        buf_str(&out, "print");
                    }
                    i = mi;
                }
                continue;
            }
            if (strncmp(word, "if", wlen) == 0 && wlen == 2) {
                buf_str(&out, "if ");
                i = wi;
                continue;
            }
            if (strncmp(word, "else", wlen) == 0 && wlen == 4) {
                buf_str(&out, "else");
                i = wi;
                continue;
            }
            if (strncmp(word, "for", wlen) == 0 && wlen == 3) {
                buf_str(&out, "for ");
                i = wi;
                continue;
            }
            if (strncmp(word, "while", wlen) == 0 && wlen == 5) {
                buf_str(&out, "while ");
                i = wi;
                continue;
            }
            if (strncmp(word, "in", wlen) == 0 && wlen == 2) {
                buf_str(&out, " in ");
                i = wi;
                continue;
            }
            if (strncmp(word, "pyimport", wlen) == 0 && wlen == 8) {
                buf_str(&out, "import ");
                i = wi;
                continue;
            }
            if (strncmp(word, "exec", wlen) == 0 && wlen == 4) {
                /* exec(var:lang, "code") → __kryp_exec_XX__("code") or exec("code") */
                i = wi;
                if (i < len && source[i] == '(') {
                    i++; /* skip ( */
                    i = skip_ws(source, i);
                    /* Check for var:lang */
                    if (strncmp(source + i, "var:", 4) == 0) {
                        i += 4;
                        char lang[16];
                        int li = read_ident(source, i, lang, sizeof(lang));
                        i = skip_ws(source, li);
                        if (source[i] == ',') i++; /* skip comma */
                        i = skip_ws(source, i);
                        /* Now read the code string */
                        if (source[i] == '"') {
                            i++; /* skip quote */
                            int cs = i;
                            while (i < len && source[i] != '"') {
                                if (source[i] == '\\') i++;
                                i++;
                            }
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
                            if (i < len) i++;
                        }
                    } else {
                        /* No var:lang → default Kryp exec → just exec() */
                        buf_str(&out, "exec(");
                        /* Copy everything until matching ) */
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
            if (strncmp(word, "true", wlen) == 0 && wlen == 4) {
                buf_str(&out, "True");
                i = wi;
                continue;
            }
            if (strncmp(word, "false", wlen) == 0 && wlen == 5) {
                buf_str(&out, "False");
                i = wi;
                continue;
            }
            if (strncmp(word, "none", wlen) == 0 && wlen == 4) {
                buf_str(&out, "None");
                i = wi;
                continue;
            }

            /* Unknown identifier → pass through */
            buf_append(&out, word, wlen);
            i = wi;
            continue;
        }

        /* => becomes : with newline handling */
        if (source[i] == '=' && source[i+1] == '>') {
            buf_str(&out, ":");
            i += 2;
            /* If rest of line is non-empty (single-line body), keep it on same line */
            int j = skip_ws(source, i);
            if (j < len && source[j] != '\n' && source[j] != '\0') {
                /* Single-line body: add space and continue */
                buf_char(&out, ' ');
            }
            /* Otherwise newline will be handled naturally */
            continue;
        }

        /* Operators */
        if (source[i] == '&' && source[i+1] == '&') { buf_str(&out, " and "); i += 2; continue; }
        if (source[i] == '|' && source[i+1] == '|') { buf_str(&out, " or "); i += 2; continue; }
        if (source[i] == '!' && source[i+1] != '=') { buf_char(&out, '!'); i++; continue; }

        /* Everything else passes through */
        buf_char(&out, source[i]);
        i++;
    }

    buf_char(&out, '\0');
    return out.buf;
}

/* ── Commands ────────────────────────────────────────────── */
static int cmd_run(const char *path) {
    const char *ext = strrchr(path, '.');
    if (ext && strcmp(ext, ".kryc") == 0) {
        char *data = read_file(path);
        if (!data) return 1;
        char *script;
        asprintf(&script,
            "import base64\n"
            "exec(base64.b64decode('''%s''').decode())\n", data);
        free(data);
        py_exec(script);
        free(script);
    } else {
        char *source = read_file(path);
        if (!source) return 1;
        char *py = transpile(source);
        free(source);
        if (!py) return 1;
        py_exec(py);
        free(py);
    }
    return 0;
}

static int cmd_compile(const char *path) {
    char *source = read_file(path);
    if (!source) return 1;
    char *py = transpile(source);
    free(source);
    if (!py) return 1;

    char *out_path;
    asprintf(&out_path, "%s.kryc", path);

    char *script;
    asprintf(&script,
        "import base64\n"
        "with open('%s','w') as f:\n"
        "    f.write(base64.b64encode(b'''%s''').decode())\n",
        out_path, py);
    py_exec(script);
    printf("✓ Compiled to %s\n", out_path);
    free(py); free(out_path); free(script);
    return 0;
}

static int cmd_install(const char *pkg) {
    char *cmd;
    asprintf(&cmd, "pip install %s", pkg);
    printf("Installing %s...\n", pkg);
    int rc = system(cmd);
    free(cmd);
    if (rc == 0) printf("✓ Installed %s\n", pkg);
    else         fprintf(stderr, "✗ Failed to install %s\n", pkg);
    return rc;
}

static void usage(void) {
    printf("Kryp v%s\n"
           "Usage:\n"
           "  kryp run <file.kryp|file.kryc>\n"
           "  kryp compile <file.kryp>\n"
           "  kryp install <package>\n", VERSION);
}

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