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
          wayland
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
          krb5.lib
          zstd.out
          brotli.lib
        ];
        uvEnv = pkgs.buildEnv {
          name = "floowandereeze-env";
          paths = [ pkgs.uv ] ++ qtLibs;
        };
        fhs = pkgs.buildFHSEnv {
          name = "floowandereeze-fhs";
          targetPkgs = pkgs: qtLibs ++ (with pkgs; [
            alsa-lib
            pulseaudio
          ]);
          runScript = pkgs.writeScript "fhs-entry.sh" ''
            if [ $# -eq 0 ]; then
              exec bash
            else
              exec "$@"
            fi
          '';
        };
      in
      {
        packages.fhs = fhs;

        devShells.default = pkgs.mkShell {
          packages = [ pkgs.uv pkgs.python312 ];
          buildInputs = qtLibs;
          LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath qtLibs;
          shellHook = ''
            export UV_PYTHON_PREFERENCE=only-managed
            unset _PYTHON_SYSCONFIGDATA_NAME
          '';
        };

        apps.default = {
          type = "app";
          program = "${uvEnv}/bin/uv";
        };

        apps.fhs = {
          type = "app";
          program = "${fhs}/bin/floowandereeze-fhs";
        };
      }
    );
}
