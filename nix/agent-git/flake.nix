{
  description = "agent-git/agent-gh: guarded git+gh for Pi agents (refuses destructive push/ref/PR ops)";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f (import nixpkgs {
        inherit system;
        overlays = [ self.overlays.default ];
      }));
    in
    {
      overlays.default = import ./overlay.nix;

      packages = forAllSystems (pkgs: {
        inherit (pkgs) agent-git agent-gh;
        default = pkgs.agent-git;
      });

      checks = forAllSystems (pkgs: {
        agent-git = pkgs.agent-git;
        agent-gh = pkgs.agent-gh;
        no-force-push = import ./tests/no-force-push.nix { inherit pkgs; };
      });
    };
}
