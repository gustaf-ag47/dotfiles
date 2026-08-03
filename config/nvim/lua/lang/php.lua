-- PHP language module
-- Dual-server setup: Intelephense (completion/diagnostics) + Phpactor (refactoring)
-- This provides maximum PHP feature parity with PhpStorm
-- Updated for Neovim 0.11+ native LSP configuration (vim.lsp.config)

local M = {}

-- Root finder that anchors at the real project root, not a sub-module.
-- Monorepo / module layouts (e.g. modules/membership/composer.json) have their
-- own composer.json but no vendor/ — we keep walking up until we find a
-- composer.json that sits next to a vendor/ directory. That is the root
-- intelephense and phpactor need to index all dependencies correctly.
local function root_pattern(...)
  local patterns = { ... }
  return function(bufnr, on_dir)
    local fname = vim.api.nvim_buf_get_name(bufnr)
    local path = vim.fn.fnamemodify(fname, ':h')
    local first_match = nil

    while path and path ~= '/' do
      for _, pattern in ipairs(patterns) do
        local target = path .. '/' .. pattern
        if vim.fn.isdirectory(target) == 1 or vim.fn.filereadable(target) == 1 then
          -- Prefer a root that has vendor/ (true project root over sub-module)
          if vim.fn.isdirectory(path .. '/vendor') == 1 then
            on_dir(path)
            return
          end
          if not first_match then
            first_match = path
          end
        end
      end
      path = vim.fn.fnamemodify(path, ':h')
    end

    on_dir(first_match or vim.fn.fnamemodify(fname, ':h'))
  end
end

-- PHP-specific plugin specifications
M.plugins = {
  -- PHP-specific IDE features (Phpactor binary for LSP)
  {
    'phpactor/phpactor',
    ft = 'php',
    build = 'composer install --no-dev --optimize-autoloader',
    config = function()
      vim.g.phpactorPhpBin = 'php'
      vim.g.phpactorBranch = 'master'
      vim.g.phpactorOmniAutoClassImport = true
    end,
  },

  -- Phpactor RPC commands (move class, import, context menu, etc.)
  {
    'gbprod/phpactor.nvim',
    ft = 'php',
    dependencies = {
      'nvim-lua/plenary.nvim',
      'neovim/nvim-lspconfig',
    },
    opts = {
      install = {
        -- Point to the phar directly — the Mason bin is a shell wrapper and
        -- phpactor.nvim calls it as `php <bin>`, which breaks on a shell script.
        bin = vim.fn.stdpath 'data' .. '/mason/packages/phpactor/phpactor.phar',
        check_on_startup = 'none',
        confirm = false,
      },
      lspconfig = { enabled = false },
    },
  },

  -- PHP method/class generation tools
  {
    'ccaglak/phptools.nvim',
    ft = 'php',
    dependencies = { 'nvim-lua/plenary.nvim' },
    opts = {},
  },

  -- PHP namespace resolver
  {
    'ccaglak/namespace.nvim',
    ft = 'php',
    dependencies = { 'nvim-lua/plenary.nvim' },
    opts = {},
  },
}

-- PHP LSP configuration
-- Uses both Intelephense (completion, diagnostics) and Phpactor (refactoring)
M.lsp_config = {
  -- Intelephense for superior auto-completion and diagnostics
  intelephense = {
    cmd = { 'intelephense', '--stdio' },
    filetypes = { 'php' },
    root_dir = root_pattern('composer.json', '.git', 'index.php'),
    settings = {
      intelephense = {
        -- Stub configuration for framework support
        stubs = {
          'apache',
          'bcmath',
          'bz2',
          'calendar',
          'com_dotnet',
          'Core',
          'ctype',
          'curl',
          'date',
          'dba',
          'dom',
          'enchant',
          'exif',
          'FFI',
          'fileinfo',
          'filter',
          'fpm',
          'ftp',
          'gd',
          'gettext',
          'gmp',
          'hash',
          'iconv',
          'imap',
          'intl',
          'json',
          'ldap',
          'libxml',
          'mbstring',
          'meta',
          'mysqli',
          'oci8',
          'odbc',
          'openssl',
          'pcntl',
          'pcre',
          'PDO',
          'pdo_ibm',
          'pdo_mysql',
          'pdo_pgsql',
          'pdo_sqlite',
          'pgsql',
          'Phar',
          'posix',
          'pspell',
          'readline',
          'Reflection',
          'session',
          'shmop',
          'SimpleXML',
          'snmp',
          'soap',
          'sockets',
          'sodium',
          'SPL',
          'sqlite3',
          'standard',
          'superglobals',
          'sysvmsg',
          'sysvsem',
          'sysvshm',
          'tidy',
          'tokenizer',
          'xml',
          'xmlreader',
          'xmlrpc',
          'xmlwriter',
          'xsl',
          'Zend OPcache',
          'zip',
          'zlib',
          -- Framework stubs
          'phpunit',
          'symfony',
        },
        -- File configuration
        files = {
          maxSize = 5000000, -- 5MB max file size
          associations = { '*.php', '*.phtml', '*.inc' },
          exclude = {
            '**/vendor/**/{Tests,tests}/**',
            '**/.git/**',
            '**/node_modules/**',
          },
        },
        -- Environment configuration
        -- Global default; override per-project via .nvim.lua using vim.lsp.config merge.
        environment = {
          phpVersion = '8.2',
          includePaths = {},
        },
        -- Completion configuration
        completion = {
          insertUseDeclaration = true,
          fullyQualifyGlobalConstantsAndFunctions = false,
          triggerParameterHints = true,
          maxItems = 100,
        },
        -- Formatting (disabled - use PHP-CS-Fixer instead)
        format = {
          enable = false,
        },
        -- Diagnostics
        diagnostics = {
          enable = true,
          run = 'onType',
          undefinedTypes = true,
          undefinedFunctions = true,
          undefinedConstants = true,
          undefinedClassConstants = true,
          undefinedMethods = true,
          undefinedProperties = true,
          undefinedVariables = true,
          unusedVariables = true,
          -- Imports used only in docblock annotations (@Groups, @Assert, @ORM, etc.)
          -- are unavoidably flagged as unused since intelephense doesn't parse docblocks
          -- for usage. Disable the broader unusedSymbols check to suppress these false
          -- positives. unusedVariables above still catches actual unused local variables.
          unusedSymbols = false,
          -- PHPUnit 7.x on PHP 7.4 lacks intersection types so createMock() returns
          -- plain MockObject, causing unavoidable false positives on every mock
          -- argument. Real type errors are covered by phpstan level 7 via nvim-lint.
          typeErrors = false,
          duplicateSymbols = true,
          argumentCount = true,
          deprecated = true,
          implementationErrors = true,
          languageConstraints = true,
        },
        -- Rename
        rename = {
          exclude = { '**/vendor/**' },
          namespaceMode = 'all', -- 'all', 'single', 'none'
        },
        -- References
        references = {
          exclude = { '**/vendor/**' },
        },
        -- Telemetry
        telemetry = {
          enabled = false,
        },
        -- Inlay hints (requires premium licence at ~/intelephense/licence.txt)
        -- Return types and param names are useful; param types are noisy in Symfony DI.
        -- Note: singular "inlayHint" — "inlayHints" (plural) is silently ignored.
        inlayHint = {
          enable = true,
          returnTypes = true,
          parameterTypes = false,
          parameterNames = true,
        },
      },
    },
    -- Disable code actions from Intelephense (use Phpactor instead)
    on_attach = function(client, bufnr)
      -- Keep completion and diagnostics, disable code actions
      client.server_capabilities.codeActionProvider = false
    end,
  },

  -- Phpactor for refactoring code actions
  phpactor = {
    cmd = { 'phpactor', 'language-server' },
    filetypes = { 'php' },
    root_dir = root_pattern('composer.json', '.git', '.phpactor.json', '.phpactor.yml'),
    init_options = {
      -- Pin PHP version for analysis (prevents phpactor using host PHP 8.x on a 7.4 project)
      ['php.version'] = '7.4',
      -- Diagnostics: phpactor is refactoring-only; intelephense owns diagnostics.
      ['language_server_worse_reflection.diagnostics.enable'] = false,
      -- Don't run diagnostics on every keypress (intelephense owns that role)
      ['language_server.diagnostics_on_update'] = false,
      -- Don't highlight references on cursor move (intelephense handles this)
      ['language_server_highlight.enabled'] = false,
      -- Suppress startup prompts to enable PHPStan/Psalm (deliberately disabled)
      ['language_server_configuration.auto_config'] = false,
      -- Symfony service container integration.
      -- Reads var/cache/dev/App_KernelDevDebugContainer.xml for service type inference.
      -- Requires: bin/console cache:warmup (run once after schema changes).
      ['symfony.enabled'] = true,
      ['symfony.xml_path'] = 'var/cache/dev/App_KernelDevDebugContainer.xml',
      -- Disable external linter integrations
      ['language_server_phpstan.enabled'] = false,
      ['language_server_psalm.enabled'] = false,
      -- Disable completion completors (intelephense handles completion)
      ['completion_worse.completor.class.enabled'] = false,
      ['completion_worse.completor.constructor.enabled'] = false,
      ['completion_worse.completor.declared_class.enabled'] = false,
      ['completion_worse.completor.declared_function.enabled'] = false,
      ['completion_worse.completor.local_variable.enabled'] = false,
      ['completion_worse.completor.scf_class.enabled'] = false,
      ['completion_worse.completor.symfony.enabled'] = false,
      -- Enable refactoring features
      ['language_server_code_transform.import_globals'] = true,
      ['language_server_reference_finder.reference_timeout'] = 10,
      ['language_server_reference_finder.soft_timeout'] = 5,
      -- Indexer: exclude generated/cache dirs to prevent OOM and slow startup
      ['indexer.exclude_patterns'] = {
        '/vendor/**/Tests/**/*',
        '/vendor/**/tests/**/*',
        '/vendor/composer/**/*',
        '/var/cache/**/*',
        '/var/log/**/*',
      },
      ['indexer.enabled_watchers'] = { 'inotify' },
      ['indexer.stub_paths'] = {},
      ['indexer.reference_finder.deep'] = true,
      ['indexer.implementation_finder.deep'] = true,
      ['code_transform.refactor.generate_accessor.prefix'] = 'get',
      ['code_transform.refactor.generate_mutator.prefix'] = 'set',
      ['code_transform.import_globals'] = true,
      ['worse_reflection.enable_cache'] = true,
    },
    -- Drop any publishDiagnostics messages phpactor still sends (belt-and-suspenders).
    -- Phpactor is refactoring-only; zero diagnostics should reach the buffer.
    handlers = {
      ['textDocument/publishDiagnostics'] = function() end,
    },
    on_attach = function(client, bufnr)
      client.server_capabilities.completionProvider = nil
      client.server_capabilities.hoverProvider = false
      client.server_capabilities.signatureHelpProvider = nil
      client.server_capabilities.documentFormattingProvider = false
      client.server_capabilities.documentRangeFormattingProvider = false
      client.server_capabilities.diagnosticProvider = nil
    end,
  },
}

-- Debug configuration for PHP (Xdebug)
M.debug_config = {
  adapters = {
    php = {
      type = 'executable',
      command = 'node',
      args = (function()
        local mason_path = vim.fn.stdpath 'data' .. '/mason/packages/php-debug-adapter/extension/out/phpDebug.js'
        if vim.fn.filereadable(mason_path) == 1 then
          return { mason_path }
        end
        -- Fallback: let mason-registry resolve it if available
        local ok, reg = pcall(require, 'mason-registry')
        if ok and reg.is_installed 'php-debug-adapter' then
          return { reg.get_package('php-debug-adapter'):get_install_path() .. '/extension/out/phpDebug.js' }
        end
        return { 'php-debug-adapter' }
      end)(),
    },
  },
  configurations = {
    php = {
      {
        type = 'php',
        request = 'launch',
        name = 'Listen for Xdebug (port 9003)',
        port = 9003,
        hostname = '0.0.0.0',
        pathMappings = {
          ['/var/www/html'] = '${workspaceFolder}',
        },
      },
      {
        type = 'php',
        request = 'launch',
        name = 'Xdebug Docker — port 9004',
        port = 9004,
        hostname = '0.0.0.0',
        -- Container mounts project root at /srv; Xdebug connects to
        -- host.docker.internal:9004 (set in docker/php/app.ini).
        pathMappings = {
          ['/srv'] = '${workspaceFolder}',
        },
        xdebugSettings = {
          maxChildren = 128,
          maxDepth = 5,
        },
        skipFiles = { '**/vendor/**' },
      },
      {
        type = 'php',
        request = 'launch',
        name = 'Launch current file',
        program = '${file}',
        cwd = '${fileDirname}',
        port = 0,
        runtimeArgs = { '-dxdebug.start_with_request=yes' },
        env = {
          XDEBUG_MODE = 'debug,develop',
          XDEBUG_CONFIG = 'client_port=${port}',
        },
      },
    },
  },
}

-- PHP-specific keymaps
M.setup_keymaps = function(bufnr)
  local opts = { buffer = bufnr, silent = true }
  local map = vim.keymap.set

  -- PHP execution
  map('n', '<leader>Pr', '<cmd>!php %<cr>', vim.tbl_extend('force', opts, { desc = 'Run PHP file' }))
  map('n', '<leader>Pl', '<cmd>!php -l %<cr>', vim.tbl_extend('force', opts, { desc = 'PHP lint' }))

  -- Composer commands
  map('n', '<leader>Pci', '<cmd>!composer install<cr>', vim.tbl_extend('force', opts, { desc = 'Composer install' }))
  map('n', '<leader>Pcu', '<cmd>!composer update<cr>', vim.tbl_extend('force', opts, { desc = 'Composer update' }))
  map('n', '<leader>Pcd', '<cmd>!composer dump-autoload<cr>', vim.tbl_extend('force', opts, { desc = 'Composer dump' }))

  -- Testing (PHPUnit via neotest — uses Docker-aware wrapper)
  map('n', '<leader>Ptt', function()
    require('neotest').run.run()
  end, vim.tbl_extend('force', opts, { desc = 'Run nearest test' }))
  map('n', '<leader>Ptf', function()
    require('neotest').run.run(vim.fn.expand '%')
  end, vim.tbl_extend('force', opts, { desc = 'Run test file' }))
  map('n', '<leader>Ptd', function()
    require('neotest').run.run { strategy = 'dap' }
  end, vim.tbl_extend('force', opts, { desc = 'Debug nearest test' }))
  map('n', '<leader>Pto', function()
    require('neotest').output.open { enter = true }
  end, vim.tbl_extend('force', opts, { desc = 'Show test output' }))

  -- Make-based test suites (integration/API tests need ephemeral DB via Make)
  local function make(target)
    return function()
      vim.cmd('botright 15split | terminal make ' .. target)
      vim.cmd 'startinsert'
    end
  end
  map('n', '<leader>Ptu', make 'test-unit', vim.tbl_extend('force', opts, { desc = 'make test-unit' }))
  map('n', '<leader>Pti', make 'test-integration', vim.tbl_extend('force', opts, { desc = 'make test-integration' }))
  map('n', '<leader>Pta', make 'test-api', vim.tbl_extend('force', opts, { desc = 'make test-api' }))
  map('n', '<leader>PtA', make 'test', vim.tbl_extend('force', opts, { desc = 'make test (all)' }))

  -- Kill whatever holds port 9004, then start a fresh DAP listener.
  -- on_ready() is called immediately after dap.run() (adapter binds asynchronously).
  local function launch_php_dap(root, on_ready)
    local dap = require 'dap'
    local function do_launch()
      pcall(function()
        require('dapui').close()
      end)
      vim.fn.jobstart('fuser -k 9004/tcp 2>/dev/null; true', {
        on_exit = function()
          vim.defer_fn(function()
            dap.run {
              type = 'php',
              request = 'launch',
              name = 'PHP Xdebug 9004',
              port = 9004,
              hostname = '0.0.0.0',
              pathMappings = { ['/srv'] = root },
            }
            if on_ready then
              on_ready()
            end
          end, 150)
        end,
      })
    end
    if dap.session() then
      dap.terminate()
      vim.defer_fn(do_launch, 300)
    else
      do_launch()
    end
  end

  -- Wait for the DAP adapter's initialized event (fired after launch handshake),
  -- then open a terminal split running cmd. Uses the event lifecycle rather than
  -- port polling so the test starts only after the adapter is ready for Xdebug.
  local function run_when_dap_ready(cmd)
    local dap = require 'dap'
    local id = 'php_autorun_' .. tostring(vim.fn.localtime())
    local fired = false
    dap.listeners.after.event_initialized[id] = function()
      if fired then
        return
      end
      fired = true
      dap.listeners.after.event_initialized[id] = nil
      vim.schedule(function()
        vim.cmd('botright 15split | terminal ' .. cmd)
        vim.cmd 'startinsert'
      end)
    end
    vim.defer_fn(function()
      if not fired then
        dap.listeners.after.event_initialized[id] = nil
        vim.notify('DAP adapter did not initialize within 10s', vim.log.levels.ERROR)
      end
    end, 10000)
  end

  -- DAP: launch the PHP listener directly (no picker)
  map('n', '<leader>PdL', function()
    launch_php_dap(vim.fn.getcwd())
  end, vim.tbl_extend('force', opts, { desc = 'DAP: launch PHP listener' }))

  -- Debug nearest integration test: set breakpoint at cursor, start DAP, run test in terminal
  map('n', '<leader>PtD', function()
    local dap = require 'dap'
    local root = vim.fn.getcwd()
    local buf = vim.api.nvim_get_current_buf()
    local line = vim.api.nvim_win_get_cursor(0)[1]
    local file = vim.api.nvim_buf_get_name(buf)

    -- Detect test type from path
    local make_target
    if file:match '[/\\]tests[/\\]Integration[/\\]' then
      make_target = 'test-integration-debug-filter'
    elseif file:match '[/\\]tests[/\\]Unit[/\\]' then
      make_target = 'test-unit-debug-filter'
    else
      vim.notify('Not a recognized test file (must be under tests/Unit/ or tests/Integration/)', vim.log.levels.WARN)
      return
    end

    -- Extract class name from filename (TestClassName.php -> TestClassName)
    local class_name = vim.fn.fnamemodify(file, ':t:r')

    -- Walk upward from cursor to find enclosing function name
    local method_name = nil
    local lines = vim.api.nvim_buf_get_lines(buf, 0, line, false)
    for i = #lines, 1, -1 do
      local m = lines[i]:match '%s*public%s+function%s+([%w_]+)'
      if m and m ~= 'setUp' and m ~= 'tearDown' then
        method_name = m
        break
      end
    end

    -- Build filter string; pass TESTFILE so phpunit loads only this file (fast with Xdebug)
    local filter = class_name
    if method_name then
      filter = class_name .. '::' .. method_name
    end
    local relative_file = vim.fn.fnamemodify(file, ':.')
    local cmd = string.format('make %s FILTER="%s" TESTFILE="%s"', make_target, filter, relative_file)

    -- Kill port, start fresh DAP listener, then wait for it to bind before running the test
    launch_php_dap(root, function()
      run_when_dap_ready(cmd)
    end)
  end, vim.tbl_extend('force', opts, { desc = 'Debug nearest integration test' }))

  -- Formatting (PHP-CS-Fixer)
  map('n', '<leader>Pf', '<cmd>!./vendor/bin/php-cs-fixer fix %<cr>', vim.tbl_extend('force', opts, { desc = 'PHP-CS-Fixer' }))
  map('n', '<leader>PF', '<cmd>!./vendor/bin/php-cs-fixer fix<cr>', vim.tbl_extend('force', opts, { desc = 'PHP-CS-Fixer all' }))

  -- Static analysis
  map('n', '<leader>Ps', '<cmd>!./vendor/bin/phpstan analyse %<cr>', vim.tbl_extend('force', opts, { desc = 'PHPStan file' }))
  map('n', '<leader>PS', '<cmd>!./vendor/bin/phpstan analyse<cr>', vim.tbl_extend('force', opts, { desc = 'PHPStan all' }))

  -- Phpactor RPC commands (via gbprod/phpactor.nvim)
  -- Navigation / file ops
  map('n', '<leader>Pn', '<cmd>PhpActor navigate<cr>', vim.tbl_extend('force', opts, { desc = 'Navigate (class↔test)' }))
  map('n', '<leader>Pm', '<cmd>PhpActor move_class<cr>', vim.tbl_extend('force', opts, { desc = 'Move/rename class' }))
  map('n', '<leader>Pco', '<cmd>PhpActor copy_class<cr>', vim.tbl_extend('force', opts, { desc = 'Copy class' }))
  map('n', '<leader>Pnc', '<cmd>PhpActor new_class<cr>', vim.tbl_extend('force', opts, { desc = 'New class from template' }))
  -- Imports / symbols
  map('n', '<leader>Pi', '<cmd>PhpActor import_missing_classes<cr>', vim.tbl_extend('force', opts, { desc = 'Import missing classes' }))
  map('n', '<leader>Pq', '<cmd>PhpActor copy_qualified_class_name<cr>', vim.tbl_extend('force', opts, { desc = 'Copy FQCN' }))
  -- Code actions
  map('n', '<leader>Pv', '<cmd>PhpActor change_visibility<cr>', vim.tbl_extend('force', opts, { desc = 'Change visibility' }))
  map('n', '<leader>Px', '<cmd>PhpActor context_menu<cr>', vim.tbl_extend('force', opts, { desc = 'Context menu' }))
  map('n', '<leader>Pa', '<cmd>PhpActor generate_accessor<cr>', vim.tbl_extend('force', opts, { desc = 'Generate accessor' }))

  -- PHP tools (ccaglak/phptools.nvim)
  map('n', '<leader>PM', '<cmd>PhpMethod<cr>', vim.tbl_extend('force', opts, { desc = 'Generate method' }))
  map('n', '<leader>PG', '<cmd>PhpGetSet<cr>', vim.tbl_extend('force', opts, { desc = 'Getter/Setter' }))
  map('n', '<leader>PC', '<cmd>PhpClass<cr>', vim.tbl_extend('force', opts, { desc = 'Create class' }))

  -- Namespace management (ccaglak/namespace.nvim)
  map('n', '<leader>Pu', '<cmd>PhpNamespace<cr>', vim.tbl_extend('force', opts, { desc = 'Find/add use statement' }))
  map('n', '<leader>PU', '<cmd>PhpNamespaceSort<cr>', vim.tbl_extend('force', opts, { desc = 'Sort use statements' }))

  -- Symfony console (replacing Laravel artisan)
  map('n', '<leader>Psc', '<cmd>!php bin/console<cr>', vim.tbl_extend('force', opts, { desc = 'Symfony console' }))
  map('n', '<leader>Psm', '<cmd>!php bin/console doctrine:migrations:migrate<cr>', vim.tbl_extend('force', opts, { desc = 'Doctrine migrate' }))
  map('n', '<leader>Pcc', '<cmd>!php bin/console cache:clear<cr>', vim.tbl_extend('force', opts, { desc = 'Cache clear' }))
end

-- PHP-specific autocommands
M.setup_autocmds = function()
  local augroup = vim.api.nvim_create_augroup('PHPConfig', { clear = true })

  -- PHP filetype settings
  vim.api.nvim_create_autocmd('FileType', {
    group = augroup,
    pattern = { 'php' },
    callback = function(event)
      -- PHP-specific editor settings
      vim.opt_local.expandtab = true
      vim.opt_local.tabstop = 4
      vim.opt_local.shiftwidth = 4
      vim.opt_local.softtabstop = 4
      vim.opt_local.textwidth = 120
      vim.opt_local.colorcolumn = '120'

      -- Include $ in keyword so hover/search captures $variable
      vim.opt_local.iskeyword:append '$'

      -- Register PHP which-key group (buffer-local)
      local wk_ok, wk = pcall(require, 'which-key')
      if wk_ok then
        wk.add {
          { '<leader>P', group = 'PHP', icon = '', buffer = event.buf },
          { '<leader>Pt', group = 'test', icon = '', buffer = event.buf },
          { '<leader>Pd', group = 'debug', icon = '', buffer = event.buf },
          { '<leader>Pc', group = 'composer', icon = '📦', buffer = event.buf },
          { '<leader>Ps', group = 'symfony', icon = '🎵', buffer = event.buf },
          { '<leader>Pr', group = 'refactor', icon = '', buffer = event.buf },
          { '<leader>PR', group = 'rector', icon = '⚡', buffer = event.buf },
        }
      end

      -- Setup PHP-specific keymaps
      M.setup_keymaps(event.buf)
    end,
  })
end

-- Tool requirements for PHP development
M.required_tools = {
  -- LSP servers
  'intelephense',
  'phpactor',

  -- Formatters
  'php-cs-fixer',

  -- Linters
  'phpstan',

  -- Debugger
  'php-debug-adapter',
}

-- Initialize the PHP module
M.setup = function()
  -- Setup autocommands for PHP files
  M.setup_autocmds()

  -- Get default capabilities
  local capabilities = vim.lsp.protocol.make_client_capabilities()
  local ok, cmp_nvim_lsp = pcall(require, 'cmp_nvim_lsp')
  if ok then
    capabilities = vim.tbl_deep_extend('force', capabilities, cmp_nvim_lsp.default_capabilities())
  end

  -- Configure and enable Intelephense using native Neovim 0.11+ API
  if M.lsp_config.intelephense then
    local config = vim.tbl_deep_extend('force', M.lsp_config.intelephense, { capabilities = capabilities })
    vim.lsp.config('intelephense', config)
    vim.lsp.enable 'intelephense'
  end

  -- Configure and enable Phpactor using native Neovim 0.11+ API
  if M.lsp_config.phpactor then
    local config = vim.tbl_deep_extend('force', M.lsp_config.phpactor, { capabilities = capabilities })
    vim.lsp.config('phpactor', config)
    vim.lsp.enable 'phpactor'
  end
end

return M
