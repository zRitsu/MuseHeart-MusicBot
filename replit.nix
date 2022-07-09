{ pkgs }: {
  deps = [
    pkgs.python310Full
    pkgs.ffmpeg
    pkgs.jdk17_headless
  ];
  env = {
    PYTHON_LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [
      pkgs.libopus
    ];
    PYTHONBIN = "${pkgs.python310Full}/bin/python3.10";
    LANG = "en_US.UTF-8";
  };
}