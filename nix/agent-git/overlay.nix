# Overlay producing `agent-git`: git with pushes to delete/force-overwrite
# refs disabled. Does not replace nixpkgs' own `git`/`gitMinimal` so the
# overlay never triggers rebuilds elsewhere in the dependency graph; only
# code that explicitly asks for `agent-git` gets the patched binary.
final: prev: {
  agent-git = import ./third_party/git { inherit (prev) git; };

  agent-gh = prev.callPackage ./agent-gh.nix { };
}
