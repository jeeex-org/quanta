/**
 * tree-sitter-quanta — grammar for the Quanta programming language.
 *
 * SCOPE: covers the syntax the 0.0.47 self-hosting compiler actually parses
 * (extracted from lexer.quanta / parse.quanta / method.quanta). It is purposely
 * PERMISSIVE: it parses the compiler's own ~317 .quanta source files so that
 * CodeRabbit / GitHub Linguist can review them. It does NOT enforce semantic
 * rules (those are the compiler's job). Future syntax (float literals, real
 * generics, tuples-in-source, etc.) should be added here per-PR as it lands.
 *
 * Verified against: compiler/0.0.47/src/x86/*.quanta (self-host source).
 */

module.exports = grammar({
  name: 'quanta',

  word: $ => $.identifier,

  extras: $ => [
    $.line_comment,
    $.block_comment,
    $.hash_comment,
    /[ \t\r\n]/,
  ],

  conflicts: $ => [
    // `match` is both a keyword and can appear in expressions; `if`/`while`/
    // `for` heads share structure; allow enum-variant `Name::Variant` vs path.
    [$.expression, $.primary_expr],
    // match-arm `identifier =>` is ambiguous with identifier-as-expression
    [$.pattern, $.primary_expr],
    [$.pattern, $.expression],
    // defer_stmt (defer call) vs call_expr
    [$.defer_stmt, $.call_expr],
    [$.defer_stmt, $.index_expr],
    [$.defer_stmt, $.field_access],
    // top_level_item with bare expression vs call_expr
    [$.top_level_item, $.call_expr],
    [$.top_level_item, $.index_expr],
    [$.top_level_item, $.field_access],
    [$.statement, $.call_expr],
    [$.statement, $.index_expr],
    [$.statement, $.field_access],
    [$.let_stmt, $.call_expr],
    [$.let_stmt, $.index_expr],
    [$.let_stmt, $.field_access],
    [$.return_stmt, $.call_expr],
    [$.return_stmt, $.index_expr],
    [$.return_stmt, $.field_access],
    [$.return_stmt, $.return_stmt],
    [$.match_arm, $.call_expr],
    [$.match_arm, $.index_expr],
    [$.match_arm, $.field_access],
  ],

  rules: {
    // ---- top level ----
    source_file: $ => repeat($.top_level_item),

    top_level_item: $ => choice(
      $.include_directive,
      $.function_decl,
      $.struct_decl,
      $.enum_decl,
      $.interface_decl,
      $.impl_decl,
      $.extern_decl,
      $.alias_decl,
      $.global_decl,
      $.unsafe_block,
      $.defer_stmt,
      $.const_decl,
      $.let_stmt,
      $.expression,
    ),

    // ---- declarations ----
    function_decl: $ => seq(
      'fn',
      field('name', $.name),
      optional($.generic_params),
      field('params', $.parameter_list),
      optional(seq(':', $.type)),
      field('body', $.block),
    ),

    generic_params: $ => seq('<', commaSep1($.identifier), '>'),

    parameter_list: $ => seq(
      '(',
      optional(commaSep1($.parameter)),
      ')',
    ),

    parameter: $ => seq(
      field('name', $.name),
      optional(seq(':', $.type)),
      optional(seq('=', $.expression)),
    ),

    struct_decl: $ => seq(
      'struct',
      field('name', $.name),
      optional($.generic_params),
      field('body', $.struct_body),
    ),

    struct_body: $ => seq(
      '{',
      optional(commaSep1($.field_decl)),
      '}',
    ),

    field_decl: $ => seq(
      field('name', $.name),
      optional(seq(':', $.type)),
    ),

    enum_decl: $ => seq(
      'enum',
      field('name', $.name),
      field('body', $.enum_body),
    ),

    enum_body: $ => seq(
      '{',
      optional(commaSep1($.enum_variant)),
      '}',
    ),

    enum_variant: $ => seq(
      field('name', $.name),
      optional(seq('(', commaSep1($.type), ')')),
    ),

    interface_decl: $ => seq(
      'interface',
      field('name', $.name),
      optional($.generic_params),
      field('body', $.block),
    ),

    impl_decl: $ => seq(
      'impl',
      field('name', $.name),
      optional($.generic_params),
      field('body', $.block),
    ),

    extern_decl: $ => seq(
      'extern',
      optional(seq('"', $.string_literal, '"')),
      field('body', $.block),
    ),

    global_decl: $ => seq(
      'global',
      $.let_stmt,
    ),

    alias_decl: $ => seq(
      'alias',
      field('name', $.name),
      '=',
      $.type,
      ';',
    ),

    const_decl: $ => seq(
      'const',
      $.let_stmt,
    ),

    // ---- statements ----
    block: $ => seq('{', repeat($.statement), '}'),

    statement: $ => choice(
      $.let_stmt,
      $.return_stmt,
      $.if_stmt,
      $.while_stmt,
      $.for_stmt,
      $.loop_stmt,
      $.match_stmt,
      $.break_stmt,
      $.continue_stmt,
      $.defer_stmt,
      $.unsafe_block,
      $.expression,
    ),

    let_stmt: $ => seq(
      'let',
      optional('mut'),
      field('name', $.name),
      optional($.generic_params),
      optional(seq(':', $.type)),
      '=',
      field('value', $.expression),
      ';',
    ),

    return_stmt: $ => seq('return', optional($.expression), optional(';')),

    if_stmt: $ => seq(
      'if',
      field('condition', $.expression),
      field('consequence', $.block),
      optional(seq('else', choice($.block, $.if_stmt))),
    ),

    while_stmt: $ => seq(
      'while',
      field('condition', $.expression),
      field('body', $.block),
    ),

    for_stmt: $ => seq(
      'for',
      field('var', $.identifier),
      'in',
      field('iterable', $.expression),
      field('body', $.block),
    ),

    loop_stmt: $ => seq('loop', field('body', $.block)),

    match_stmt: $ => seq(
      'match',
      field('subject', $.expression),
      '{',
      optional(repeat($.match_arm)),
      '}',
    ),

    match_arm: $ => seq(
      $.pattern,
      '=>',
      choice($.block, $.expression),
    ),

    pattern: $ => choice(
      $.identifier,                 // Some, None, Ok, Err, variant name
      $.enum_path,                  // Option::Some
      '_',                          // wildcard arm
      $.expression,
    ),

    break_stmt: $ => seq('break'),
    continue_stmt: $ => seq('continue'),

    defer_stmt: $ => seq('defer', $.expression),

    include_directive: $ => seq('include', $.string_literal),

    unsafe_block: $ => seq('unsafe', $.block),

    // ---- expressions ----
    expression: $ => choice(
      $.primary_expr,
      $.binary_expr,
      $.unary_expr,
      $.call_expr,
      $.field_access,
      $.enum_path,
      $.index_expr,
      $.closure_literal,
      $.mk_any,
      $.assignment,
    ),

    primary_expr: $ => choice(
      $.identifier,
      $.int_literal,
      $.string_literal,
      $.bool_literal,
      $.unit_literal,
      $.array_literal,
      $.paren_expr,
      $.option_literal,
      $.result_literal,
    ),

    paren_expr: $ => seq('(', $.expression, ')'),

    unit_literal: $ => seq('(', ')'),

    int_literal: $ => choice(
      /0[xX][0-9a-fA-F]+/,
      /[0-9]+/,
      seq('-', /[0-9]+/),
    ),

    string_literal: $ => token(seq(
      '"',
      repeat(choice(/[^"\\]/, /\\./)),
      '"',
    )),

    bool_literal: $ => choice('true', 'false'),

    array_literal: $ => seq('[', optional(commaSep1($.expression)), ']'),

    option_literal: $ => seq('Option', '::', choice('Some', 'None')),

    result_literal: $ => seq('Result', '::', choice('Ok', 'Err')),

    binary_expr: $ => prec.left(2, seq(
      $.expression,
      $.binary_op,
      $.expression,
    )),

    binary_op: $ => token(choice(
      '+', '-', '*', '/', '%',
      '==', '!=', '<', '>', '<=', '>=',
      '&&', '||', '&', '|', '^', '<<', '>>',
      '=?', // the `?` propagation operator (IR_TRY)
    )),

    unary_expr: $ => prec.right(3, seq(
      $.unary_op,
      $.expression,
    )),

    unary_op: $ => token(choice('-', '!', '~', '*')),

    call_expr: $ => seq(
      field('function', $.expression),
      field('arguments', $.argument_list),
    ),

    argument_list: $ => seq('(', optional(commaSep1($.expression)), ')'),

    field_access: $ => seq(
      $.expression,
      '.',
      field('field', $.identifier),
    ),

    index_expr: $ => seq(
      $.expression,
      '[',
      $.expression,
      ']',
    ),

    enum_path: $ => seq(
      field('enum', $.identifier),
      '::',
      field('variant', $.identifier),
    ),

    closure_literal: $ => seq(
      'fn',
      optional($.parameter_list),
      field('body', $.block),
    ),

    mk_any: $ => seq(
      'mk_any',
      '(',
      $.expression,
      ',',
      $.expression,
      ')',
    ),

    assignment: $ => prec.right(1, seq(
      $.expression,
      '=',
      $.expression,
    )),

    // ---- types ----
    type: $ => choice(
      $.identifier,
      $.array_type,
      $.ref_type,
    ),

    array_type: $ => seq('[', $.type, ';', $.expression, ']'),

    ref_type: $ => seq(optional('mut'), 'ref', optional($.type)),

    // ---- comments ----
    line_comment: $ => token(seq('//', /[^\n]*/)),
    block_comment: $ => token(seq('/*', /[^*]*\*+([^/*][^*]*\*+)*/, '/')),
    hash_comment: $ => token(seq('#', /[^\n]*/)),

    // ---- leaves ----
    // `name` accepts identifiers AND reserved keywords, because the Quanta
    // compiler's own source uses keywords as function/struct/enum names
    // (e.g. `fn match(...)`, `fn if(...)`). A permissive tooling grammar must
    // allow this so CodeRabbit can review the compiler source.
    name: $ => choice(
      $.identifier,
      'fn', 'let', 'if', 'else', 'while', 'for', 'return', 'break', 'continue',
      'loop', 'struct', 'enum', 'match', 'interface', 'impl', 'extern', 'unsafe',
      'alias', 'global', 'defer', 'const', 'in', 'panic', 'type', 'where',
      'Option', 'Some', 'None', 'Result', 'Ok', 'Err', 'String', 'ref', 'mut', 'move',
    ),

    identifier: $ => /[a-zA-Z_][a-zA-Z0-9_]*/,
  },
});

function commaSep1(rule) {
  return seq(rule, repeat(seq(',', rule)));
}
