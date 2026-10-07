# Git with patches that refuse destructive pushes, for use by Pi agents only.
#
# Patches 001 and 002 are copied near-verbatim from Geoffrey Huntley's
# nix-demo (https://github.com/ghuntley/nix-demo, https://ghuntley.com/nix/),
# credited here per its SPDX header. Patch 003 extends the same approach to
# --mirror, --prune, --delete/-d and `:ref` deletion refspecs, per this
# repo's agent-git guard (see docs/agent-git.md).
#
# Patches are numbered and named by purpose:
#   001-disable-force-push.patch                  - disables `git push --force`/`-f`
#   002-disable-force-with-lease-and-plus-refspec.patch
#       - disables --force-with-lease, +refspec and other forced ref updates
#         (config refspecs, --mirror's force bit, send-pack --force)
#   003-disable-mirror-prune-and-delete.patch
#       - disables --mirror, --prune, --delete/-d and `:ref` deletion refspecs
#
# Usage in overlay:
#   git = import ./third_party/git { inherit (prev) git; };
{ git }:

let
  customPatches = [
    ./001-disable-force-push.patch
    ./002-disable-force-with-lease-and-plus-refspec.patch
    ./003-disable-mirror-prune-and-delete.patch
  ];
  patchNames = map baseNameOf customPatches;
  existingPatchNames = map baseNameOf (git.patches or [ ]);
  newPatches = builtins.filter (p: !(builtins.elem (baseNameOf p) existingPatchNames)) customPatches;
in
git.overrideAttrs (oldAttrs: {
  patches = (oldAttrs.patches or [ ]) ++ newPatches;
  doCheck = false;
  doInstallCheck = false;
})
