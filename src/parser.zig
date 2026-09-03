const std = @import("std");
const error_formatter = @import("error_formatter.zig");

pub const Ast = struct {
    nodes: std.ArrayList(Node),
    errors: std.ArrayList(Error),
    allocator: std.mem.Allocator,

    pub fn deinit(self: *Ast) void {
        self.nodes.deinit();
        self.errors.deinit();
    }
};

pub const Node = union(enum) {
    var_decl: struct { name: []const u8, value: Expr },
    fn_def: struct { name: []const u8, params: [][]const u8, body: Body },
    exec_call: struct { lang: ?[]const u8, code: Expr },
    console_call: struct { method: []const u8, args: []Expr },
    if_stmt: struct { cond: Expr, then_body: Body, else_body: ?Body },
    for_loop: struct { var_name: []const u8, iter: Expr, body: Body },
    while_loop: struct { cond: Expr, body: Body },
    pyimport: struct { module: []const u8, alias: ?[]const u8 },
    expr_stmt: Expr,
};

pub const Body = union(enum) {
    single: Expr,
    block: []Node,
};

pub const Expr = union(enum) {
    ident: []const u8,
    string: []const u8,
    number: f64,
    bool_val: bool,
    none: void,
    call: struct { func: Expr, args: []Expr },
    interp_string: struct { parts: []StringPart },
    binary_op: struct { op: []const u8, left: Expr, right: Expr },
};

pub const StringPart = union(enum) {
    literal: []const u8,
    var_ref: []const u8,
};

pub const Error = struct {
    code: []const u8,
    message: []const u8,
    line: usize,
    col: usize,
    hint: ?[]const u8,
    fix: ?[]const u8,
};

pub fn parse(allocator: std.mem.Allocator, source: []const u8, filename: []const u8) !Ast {
    var ast = Ast{
        .nodes = std.ArrayList(Node).init(allocator),
        .errors = std.ArrayList(Error).init(allocator),
        .allocator = allocator,
    };
    errdefer ast.deinit();

    // Simplified recursive descent parser placeholder
    // Full implementation would tokenize + parse according to Kryp spec
    // For now, demonstrates structure; real impl handles all syntax forms

    return ast;
}