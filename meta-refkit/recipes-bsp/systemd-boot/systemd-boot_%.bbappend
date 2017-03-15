FILESEXTRAPATHS_prepend := "${THISDIR}/files:"

SRC_URI += "file://0001-sd-boot-stub-check-LoadOptions-contains-data-5467.patch"

do_compile_append() {
	oe_runmake linux${SYSTEMD_BOOT_EFI_ARCH}.efi.stub
}

do_deploy_append () {
	install ${B}/linux*.efi.stub ${DEPLOYDIR}
}
