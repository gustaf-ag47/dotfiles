local ls = require 'luasnip'
local s = ls.snippet
local t = ls.text_node
local i = ls.insert_node

return {
  s('anki', {
    t { '%%anki%%', 'type: ' },
    i(1, 'basic'),
    t { '', 'front: ' },
    i(2, 'Question'),
    t { '', 'back: ' },
    i(3, 'Answer'),
    t { '', 'tags: ' },
    i(4, 'Tag1, Tag2'),
    t { '', '%%end%%' },
  }),
}
