const std = @import("std");
const parser = @import("parser.zig");

pub fn print(err: parser.Error, source: []const u8, filename: []const u8) void {
    const lines = std.mem.splitScalar(u8, source, '\n');
    var line_iter = lines;
    var current_line: usize = 1;
    var context_start: usize = 0;
    var context_lines: [5][]const u8 = undefined;
    var ctx_count: usize = 0;

    // Extract context around error line
    while (line_iter.next()) |line| : (current_line += 1) {
        if (current_line >= err.line - 2 and current_line <= err.line + 2) {
            if (ctx_count < 5) {
                context_lines[ctx_count] = line;
                ctx_count += 1;
            }
        }
    }

    std.debug.print("\x1b[31m✗ Kryp Error [{s}] in {s}:{d}:{d}\x1b[0m\n", .{
        err.code, filename, err.line, err.col,
    });
    std.debug.print("│\n", .{});

    for (context_lines[0..ctx_count], 0..) |line, i| {
        const line_num = err.line - 2 + i;
        std.debug.print("│ {d:3} │ {s}\n", .{ line_num, line });
        if (line_num == err.line) {
            std.debug.print("│     │ {s}^ {s}\n", .{
                " " ** (err.col - 1),
                err.message,
            });
        }
    }

    std.debug.print("│\n", .{});
    if (err.hint) |hint| {
        std.debug.print("\x1b[33m┌─ Hint: {s}\x1b[0m\n", .{hint});
    }
    if (err.fix) |fix| {
        std.debug.print("\x1b[32m└─ Fix: {s}\x1b[0m\n", .{fix});
    }
    std.debug.print("\n", .{});
}