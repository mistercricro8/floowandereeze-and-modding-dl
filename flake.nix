{
  description = "Floowandereeze & Modding - Duel Links";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs?ref=nixos-26.05";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      nixpkgs,
      flake-utils,
      ...
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = import nixpkgs {
          inherit system;
          config.allowUnfree = true;
        };
        qtLibs = with pkgs; [
          libGL
          libglvnd
          libxkbcommon
          libX11
          libXext
          libXi
          libXrender
          libXrandr
          libXfixes
          libXcomposite
          libXdamage
          libXtst
          libxcb
          xcbutil
          xcbutilimage
          xcbutilkeysyms
          xcbutilrenderutil
          xcbutilwm
          fontconfig
          freetype
          dbus
          nspr
          nss
          stdenv.cc.cc
          zlib
          glib
        ];
        uvEnv = pkgs.buildEnv {
          name = "floowandereeze-env";
          paths = [ pkgs.uv ] ++ qtLibs;
        };
      in
      {
        devShells.default = pkgs.mkShell {
          packages = [ pkgs.uv pkgs.python3 ];
          buildInputs = qtLibs;
          LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath qtLibs;
          shellHook = ''
            export UV_PYTHON_PREFERENCE=only-managed
          '';
        };

        apps.default = {
          type = "app";
          program = "${uvEnv}/bin/uv";
        };
      }
    );
}
