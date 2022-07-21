{ pkgs }: {
  deps = [
    pkgs.python38Full
    pkgs.jdk17_headless
  ];
  env = {
    PYTHONBIN = "${pkgs.python38Full}/bin/python3.8";
    LANG = "en_US.UTF-8";
  };
}