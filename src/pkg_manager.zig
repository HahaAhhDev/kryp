const std = @import("std");

pub fn install(allocator: std.mem.Allocator, package: []const u8) !void {
    std.debug.print("Installing {s} via pip...\n", .{package});

    var child = std.process.Child.init(&.{ "pip", "install", package }, allocator);
    child.stdout_behavior = .Inherit;
    child.stderr_behavior = .Inherit;

    const term = try child.spawnAndWait();
    if (term.Exited != 0) {
        std.debug.print("✗ Failed to install {s}\n", .{package});
        return error.InstallFailed;
    }

    std.debug.print("✓ Successfully installed {s}\n", .{package});
}