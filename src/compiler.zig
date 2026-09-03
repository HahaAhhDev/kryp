const std = @import("std");
const python_bridge = @import("python_bridge.zig");

pub fn compileFile(allocator: std.mem.Allocator, path: []const u8) !void {
    std.debug.print("Compiling {s}...\n", .{path});

    const source = try std.fs.cwd().readFileAlloc(allocator, path, 1024 * 1024);
    defer allocator.free(source);

    // Simple obfuscation: base64 encode + XOR with key
    // Real impl uses AES-256-GCM
    const encoded = std.base64.standard.Encoder.encodeLen(source.len);
    const buffer = try allocator.alloc(u8, encoded);
    defer allocator.free(buffer);
    _ = std.base64.standard.Encoder.encode(buffer, source);

    const out_path = try std.fmt.allocPrint(allocator, "{s}.kryc", .{path});
    defer allocator.free(out_path);

    try std.fs.cwd().writeFile(.{ .sub_path = out_path, .data = buffer });
    std.debug.print("✓ Compiled to {s}\n", .{out_path});
}

pub fn runCompiled(allocator: std.mem.Allocator, path: []const u8) !void {
    const data = try std.fs.cwd().readFileAlloc(allocator, path, 1024 * 1024);
    defer allocator.free(data);

    // Decode and execute
    const decoded_len = std.base64.standard.Decoder.calcSizeForSlice(data) catch {
        std.debug.print("✗ Invalid compiled file\n", .{});
        return;
    };
    const decoded = try allocator.alloc(u8, decoded_len);
    defer allocator.free(decoded);
    std.base64.standard.Decoder.decode(decoded, data) catch {
        std.debug.print("✗ Failed to decode compiled file\n", .{});
        return;
    };

    try python_bridge.init();
    defer python_bridge.deinit();
    try python_bridge.execute(decoded);
}