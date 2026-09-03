const std = @import("std");
const c = @cImport({
    @cInclude("Python.h");
});

pub fn init() !void {
    c.Py_Initialize();
    if (c.Py_IsInitialized() == 0) {
        return error.PythonInitFailed;
    }
    // Inject Kryp runtime helpers
    const runtime =
        \\def __kryp_console_error__(msg):
        \\    import sys
        \\    print(f"\033[91m{msg}\033[0m", file=sys.stderr)
        \\
        \\def __kryp_exec_js__(code):
        \\    import subprocess
        \\    result = subprocess.run(['node', '-e', code], capture_output=True, text=True)
        \\    if result.stdout: print(result.stdout, end='')
        \\    if result.stderr: print(result.stderr, end='', file=sys.stderr)
        \\
        \\def __kryp_exec_sh__(code):
        \\    import subprocess
        \\    result = subprocess.run(code, shell=True, capture_output=True, text=True)
        \\    if result.stdout: print(result.stdout, end='')
        \\    if result.stderr: print(result.stderr, end='', file=sys.stderr)
    ;
    _ = c.PyRun_SimpleString(runtime.ptr);
}

pub fn deinit() void {
    c.Py_Finalize();
}

pub fn execute(code: []const u8) !void {
    const c_code = try std.cstr.addNullTerminator(std.heap.page_allocator, code);
    defer std.heap.page_allocator.free(c_code);

    const result = c.PyRun_SimpleString(c_code.ptr);
    if (result != 0) {
        // Error already printed by Python; could capture and reformat
        return error.PythonExecFailed;
    }
}