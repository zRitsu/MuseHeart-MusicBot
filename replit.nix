{pkgs}: {
  deps = [
    pkgs.jdk17_headless
    pkgs.glib
    pkgs.libopus
    pkgs.zlib
    pkgs.glibc
  ];
}
