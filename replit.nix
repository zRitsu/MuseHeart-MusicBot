{ pkgs }: {
  deps = [
    pkgs.python310Full
    pkgs.replitPackages.prybar-python310
    pkgs.replitPackages.stderred
    pkgs.jdk17_headless
  ];
  env = {
    PYTHON_LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [
      pkgs.stdenv.cc.cc.lib
      pkgs.zlib
      pkgs.xorg.libX11
      pkgs.libopus
    ];
    PYTHONBIN = "${pkgs.python310Full}/bin/python3.10";
    LANG = "en_US.UTF-8";
    STDERREDBIN = "${pkgs.replitPackages.stderred}/bin/stderred";
    PRYBAR_PYTHON_BIN = "${pkgs.replitPackages.prybar-python310}/bin/prybar-python310";
  };
}