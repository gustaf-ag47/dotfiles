return {
  s(
    { trig = 'testa' }, -- Table of snippet parameters
    {
      t 'Hello, world!',
    }
  ),

  -- Combining text and insert nodes to create basic LaTeX commands
  s({ trig = 'tt', dscr = "Expands 'tt' into '\texttt{}'" }, {
    t '\\texttt{', -- remember: backslashes need to be escaped
    i(1),
    t '}',
  }),
  -- Yes, these jumbles of text nodes and insert nodes get messy fast, and yes,
  -- there is a much better, human-readable solution: ls.fmt, described shortly.
  s({ trig = 'ff', dscr = "Expands 'ff' into '\frac{}{}'" }, {
    t '\\frac{',
    i(1), -- insert node 1
    t '}{',
    i(2), -- insert node 2
    t '}',
  }),

  s({ trig = 'df', snippetType = 'autosnippet' }, { t '\\diff' }),

  s('beg', {
    t { '\\begin{' },
    i(1, 'environment'),
    t { '}', '' },
    i(0),
    t { '', '\\end{' },
    i(1),
    t { '}' },
  }),
  s('sec', {
    t { '\\section{' },
    i(1, 'Section Title'),
    t { '}' },
  }),
}
