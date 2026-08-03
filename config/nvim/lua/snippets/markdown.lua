local ls = require 'luasnip'
local s = ls.snippet
local t = ls.text_node
local i = ls.insert_node
local f = ls.function_node
local c = ls.choice_node

-- Auto-generate UUID
local function uuid()
  local handle = io.popen('uuidgen 2>/dev/null || python3 -c "import uuid; print(uuid.uuid4())"')
  if handle then
    local result = handle:read('*a'):gsub('%s+$', '')
    handle:close()
    return result
  end
  return ''
end

-- Read YAML frontmatter from current buffer
local function get_frontmatter()
  local lines = vim.api.nvim_buf_get_lines(0, 0, 30, false)
  local fm = {}
  local in_fm = false
  for _, line in ipairs(lines) do
    if line:match('^---') then
      if in_fm then break end
      in_fm = true
    elseif in_fm and line:match(':') then
      local key, val = line:match('^(%S+):%s*"?(.-)"?%s*$')
      if key and val then
        fm[key] = val
      end
    end
  end
  return fm
end

-- Build context string from frontmatter
local function auto_context()
  local fm = get_frontmatter()
  local parts = {}
  if fm.title and fm.title ~= '' then table.insert(parts, fm.title) end
  if fm.author and fm.author ~= '' then table.insert(parts, fm.author) end
  return table.concat(parts, ' - ')
end

-- Build default tag from filename
local function auto_tag()
  local fm = get_frontmatter()
  if fm.title and fm.title ~= '' then
    return fm.title:gsub('%s+', '-'):gsub('[^%w-]', ''):lower()
  end
  return vim.fn.expand('%:t:r')
end

return {
  -- Basic flashcard with auto-context from frontmatter
  s({ trig = 'anki', dscr = 'Anki basic flashcard' }, {
    t { '%%anki%%', 'id: ' },
    f(function() return uuid() end),
    t { '', 'type: basic', '', 'front: ' },
    i(1, 'Question'),
    t { '', 'back: ' },
    i(2, 'Answer'),
    t { '', 'tags: ' },
    f(function() return auto_tag() end),
    t ', ',
    i(3),
    t { '', 'context: ' },
    f(function() return auto_context() end),
    t { '', '%%end%%' },
  }),

  -- Cloze deletion flashcard
  s({ trig = 'ankic', dscr = 'Anki cloze flashcard' }, {
    t { '%%anki%%', 'id: ' },
    f(function() return uuid() end),
    t { '', 'type: cloze', '', 'front: ' },
    i(1, '{{c1::answer}} is the question'),
    t { '', 'tags: ' },
    f(function() return auto_tag() end),
    t ', ',
    i(2),
    t { '', 'context: ' },
    f(function() return auto_context() end),
    t { '', '%%end%%' },
  }),

  -- Quick card (no context, minimal)
  s({ trig = 'ankiq', dscr = 'Quick Anki card' }, {
    t { '%%anki%%', 'id: ' },
    f(function() return uuid() end),
    t { '', 'type: ' },
    c(1, {
      t 'basic',
      t 'cloze',
    }),
    t { '', 'front: ' },
    i(2, 'Question'),
    t { '', 'back: ' },
    i(3, 'Answer'),
    t { '', 'tags: ' },
    i(4),
    t { '', '%%end%%' },
  }),
}
