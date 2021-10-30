{ pkgs ? import <nixpkgs> {} }:

pkgs.python3Packages.buildPythonApplication {
  pname = "mpvinfod";
  src = ./.;
  version = "0.1";
  propagatedBuildInputs = [ pkgs.python3Packages.inotify-simple ];
}
