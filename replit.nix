{pkgs}: {
  deps = [
    pkgs.taskflow
    pkgs.rapidfuzz-cpp
    pkgs.gettext
    pkgs.cacert
    pkgs.jdk17_headless
    pkgs.glib
    pkgs.libopus
    pkgs.zlib
    #pkgs.glibc
    pkgs.chromium
  ];
}
