{pkgs}: {
  deps = [
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
