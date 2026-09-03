const std = @import("std");
const parser = @import("parser.zig");
const transpiler = @import("transpiler.zig");
const python_bridge = @import("python_bridge.zig");
const pkg_manager = @import("pkg_manager.zig");
const error_formatter = @import("error_formatter.zig");
const compiler = @import("compiler.zig");

pub fn main() !void {
    var gpa = std.heap.GeneralPurposeAllocator(.{}){};
    defer _ = gpa.deinit();
    const allocator = gpa.allocator();

    const args = try std.process.argsAlloc(allocator);
    defer std.process.argsFree(allocator, args);

    if (args.len < 2) {
        std.debug.print("Usage: kryp <run|compile|install> <file|package>\n", .{});
        return;
    }

    const command = args[1];
    if (std.mem.eql(u8, command, "run")) {
        if (args.len < 3) {
            std.debug.print("Usage: kryp run <file.kryp|file.kryc>\n", .{});
            return;
        }
        try runFile(allocator, args[2]);
    } else if (std.mem.eql(u8, command, "compile")) {
        if (args.len < 3) {
            std.debug.print("Usage: kryp compile <file.kryp>\n", .{});
            return;
        }
        try compiler.compileFile(allocator, args[2]);
    } else if (std.mem.eql(u8, command, "install")) {
        if (args.len < 3) {
            std.debug.print("Usage: kryp install <package>\n", .{});
            return;
        }
        try pkg_manager.install(allocator, args[2]);
    } else {
        std.debug.print("Unknown command: {s}\n", .{command});
    }
}

fn runFile(allocator: std.mem.Allocator, path: []const u8) !void {
    const ext = std.fs.path.extension(path);
    if (std.mem.eql(u8, ext, ".kryc")) {
        try compiler.runCompiled(allocator, path);
    } else {
        const source = try std.fs.cwd().readFileAlloc(allocator, path, 1024 * 1024);
        defer allocator.free(source);

        var ast = try parser.parse(allocator, source, path);
        defer ast.deinit();

        if (ast.errors.len > 0) {
            for (ast.errors) |err| {
                error_formatter.print(err, source, path);
            }
            return;
        }

        const python_code = try transpiler.transpile(allocator, ast);
        defer allocator.free(python_code);

        try python_bridge.init();
        defer python_bridge.deinit();
        try python_bridge.execute(python_code);
    }
}