const std = @import("std");
const parser = @import("parser.zig");

pub fn transpile(allocator: std.mem.Allocator, ast: parser.Ast) ![]u8 {
    var output = std.ArrayList(u8).init(allocator);
    errdefer output.deinit();

    for (ast.nodes.items) |node| {
        switch (node) {
            .var_decl => |v| {
                try output.writer().print("{s} = ", .{v.name});
                try emitExpr(output.writer(), v.value);
                try output.append('\n');
            },
            .fn_def => |f| {
                try output.writer().print("def {s}(", .{f.name});
                for (f.params, 0..) |param, i| {
                    if (i > 0) try output.appendSlice(", ");
                    try output.appendSlice(param);
                }
                try output.appendSlice("):\n");
                try emitBody(output.writer(), f.body, 1);
            },
            .exec_call => |e| {
                if (e.lang) |lang| {
                    if (std.mem.eql(u8, lang, "python")) {
                        try output.appendSlice("exec(");
                        try emitExpr(output.writer(), e.code);
                        try output.appendSlice(")\n");
                    } else if (std.mem.eql(u8, lang, "js")) {
                        try output.appendSlice("__kryp_exec_js__(");
                        try emitExpr(output.writer(), e.code);
                        try output.appendSlice(")\n");
                    } else if (std.mem.eql(u8, lang, "sh")) {
                        try output.appendSlice("__kryp_exec_sh__(");
                        try emitExpr(output.writer(), e.code);
                        try output.appendSlice(")\n");
                    }
                } else {
                    // Default: Kryp code → transpile recursively
                    try output.appendSlice("# Kryp exec default\n");
                }
            },
            .console_call => |c| {
                if (std.mem.eql(u8, c.method, "log")) {
                    try output.appendSlice("print(");
                } else if (std.mem.eql(u8, c.method, "error")) {
                    try output.appendSlice("__kryp_console_error__(");
                } else {
                    try output.appendSlice("print(");
                }
                for (c.args, 0..) |arg, i| {
                    if (i > 0) try output.appendSlice(", ");
                    try emitExpr(output.writer(), arg);
                }
                try output.appendSlice(")\n");
            },
            .pyimport => |p| {
                if (p.alias) |alias| {
                    try output.writer().print("import {s} as {s}\n", .{ p.module, alias });
                } else {
                    try output.writer().print("import {s}\n", .{p.module});
                }
            },
            .if_stmt => |i| {
                try output.appendSlice("if ");
                try emitExpr(output.writer(), i.cond);
                try output.appendSlice(":\n");
                try emitBody(output.writer(), i.then_body, 1);
                if (i.else_body) |eb| {
                    try output.appendSlice("else:\n");
                    try emitBody(output.writer(), eb, 1);
                }
            },
            .for_loop => |f| {
                try output.writer().print("for {s} in ", .{f.var_name});
                try emitExpr(output.writer(), f.iter);
                try output.appendSlice(":\n");
                try emitBody(output.writer(), f.body, 1);
            },
            .while_loop => |w| {
                try output.appendSlice("while ");
                try emitExpr(output.writer(), w.cond);
                try output.appendSlice(":\n");
                try emitBody(output.writer(), w.body, 1);
            },
            .expr_stmt => |e| {
                try emitExpr(output.writer(), e);
                try output.append('\n');
            },
        }
    }

    return output.toOwnedSlice();
}

fn emitExpr(writer: anytype, expr: parser.Expr) !void {
    switch (expr) {
        .ident => |id| try writer.print("{s}", .{id}),
        .string => |s| try writer.print("\"{s}\"", .{s}),
        .number => |n| try writer.print("{d}", .{n}),
        .bool_val => |b| try writer.print("{s}", .{if (b) "True" else "False"}),
        .none => try writer.print("None", .{}),
        .call => |c| {
            try emitExpr(writer, c.func);
            try writer.print("(", .{});
            for (c.args, 0..) |arg, i| {
                if (i > 0) try writer.print(", ", .{});
                try emitExpr(writer, arg);
            }
            try writer.print(")", .{});
        },
        .interp_string => |is| {
            try writer.print("f\"", .{});
            for (is.parts) |part| {
                switch (part) {
                    .literal => |lit| try writer.print("{s}", .{lit}),
                    .var_ref => |vr| try writer.print("{{{s}}}", .{vr}),
                }
            }
            try writer.print("\"", .{});
        },
        .binary_op => |op| {
            try writer.print("(", .{});
            try emitExpr(writer, op.left);
            try writer.print(" {s} ", .{op.op});
            try emitExpr(writer, op.right);
            try writer.print(")", .{});
        },
    }
}

fn emitBody(writer: anytype, body: parser.Body, indent: usize) !void {
    const spaces = "    " ** 10; // Max 10 levels
    const prefix = spaces[0 .. indent * 4];
    switch (body) {
        .single => |expr| {
            try writer.print("{s}", .{prefix});
            try emitExpr(writer, expr);
            try writer.print("\n", .{});
        },
        .block => |nodes| {
            // In real impl, recursively transpile nodes with increased indent
            _ = nodes;
            try writer.print("{s}pass\n", .{prefix});
        },
    }
}