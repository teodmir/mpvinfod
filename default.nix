{ pkgs ? import <nixpkgs> {} }:

pkgs.python3Packages.buildPythonApplication {
  pname = "mpvinfo";
  src = ./.;
  version = "0.1";
  propagatedBuildInputs = [ pkgs.python3Packages.inotify-simple ];
}
