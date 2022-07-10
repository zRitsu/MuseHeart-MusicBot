{ pkgs }: {
  deps = [
    pkgs.python38Full
    pkgs.ffmpeg
    pkgs.jdk17_headless
  ];
  env = {
    PYTHON_LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [
      pkgs.libopus
    ];
    PYTHONBIN = "${pkgs.python38Full}/bin/python3.8";
    LANG = "en_US.UTF-8";
  };
}