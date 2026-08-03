; extends

; Capture simple variable assignments as definitions so nvim-dap-virtual-text
; can place inline variable values at assignment sites during debug sessions.
; The base php_only/locals.scm only captures parameters, foreach vars, and
; anonymous function use-clause vars — not $var = expr assignments.
(assignment_expression
  left: (variable_name
    (name) @local.definition.var))
