SUMMARY = "Neard wifi agent"
DESCRIPTION = "${SUMMARY}"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI += " \
    file://neard-wifi-agent.py \
    file://neard-wifi-agent.service \
    file://org.refkit.neard.conf \
    file://LICENSE \
    "

DEPENDS += "python-dbus python-pygobject"

do_install() {
    mkdir -p ${D}/${bindir}
    mkdir -p ${D}/${systemd_system_unitdir}
    mkdir -p ${D}/${sysconfdir}/dbus-1/system.d

    cp ${WORKDIR}/neard-wifi-agent.py ${D}/${bindir}/
    cp ${WORKDIR}/neard-wifi-agent.service ${D}/${systemd_system_unitdir}/
    cp ${WORKDIR}/org.refkit.neard.conf ${D}/${sysconfdir}/dbus-1/system.d/
}

FILES_${PN} = " \
    ${bindir}/neard-wifi-agent.py \
    ${systemd_system_unitdir}/neard-wifi-agent.service \
    ${sysconfdir}/dbus-1/system.d/org.refkit.neard.conf \
    "
RDEPENDS_${PN} = "neard"
