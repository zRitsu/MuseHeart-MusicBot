{ pkgs }: {
  deps = [
    pkgs.jdk17_headless
    pkgs.ffmpeg
  ];
  env = {
    PYTHON_LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [
      pkgs.libopus
    ];
    LANG = "en_US.UTF-8";
  };
}