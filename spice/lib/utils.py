#!/usr/bin/env python

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.

"""Common spice test utility functions.

.. todo:: Rework migration, add migration as a option of the session, but
that can wait.

    xwininfo

"""
import logging
import os
import re
import sys
import time
import tempfile
import subprocess
from distutils import util
import aexpect
from virttest import qemu_vm
from virttest import remote
from virttest import utils_misc
from virttest.staging import service
from avocado.core import exceptions
from spice.lib import deco

logger = logging.getLogger(__name__)

SSL_TYPE_IMPLICIT = "implicit_hs"
"""SSL type - implicit host name."""
SSL_TYPE_EXPLICIT = "explicit_hs"
"""SSL type - explicit host name."""
SSL_TYPE_IMPLICIT_INVALID = "invalid_implicit_hs"
"""SSL type - invalid implicit host name."""
SSL_TYPE_EXPLICIT_INVALID = "invalid_explicit_hs"
"""SSL type - invalid explicit host name."""
PTRN_QEMU_SSL_ACCEPT_FAILED = "SSL_accept failed"
"""Pattern for qemu log - failed to accept SSL."""
USB_POLICY_FILE = \
    "/usr/share/polkit-1/actions/org.spice-space.lowlevelusbaccess.policy"
"""USB policy file. Location on client."""
DEPS_DIR = "deps"
"""Dir with useful files."""
USB_POLICY_FILE_SRC = os.path.join(DEPS_DIR,
                                   "org.spice-space.lowlevelusbaccess.policy")
"""USB policy file source."""

VV_DISTR_PATH = r'C:\virt-viewer.msi'
USBCLERK_DISTR_PATH = r'C:\usbclerk.msi'
"""Path to virt-viewer distribution."""
# ..todo:: add to configs: host_path. client_path + rename to more obvious.
DISPLAY = "qxl-0"


def vm_is_win(self):
    """Extention to qemu.VM(virt_vm.BaseVM) class.
    """
    if self.params.get("os_type") == "windows":
        return True
    return False


def vm_is_linux(self):
    """Extention to qemu.VM(virt_vm.BaseVM) class.
    """
    if self.params.get("os_type") == "linux":
        return True
    return False


def vm_is_rhel7(self):
    """Extention to qemu.VM(virt_vm.BaseVM) class.
    """
    if self.params.get("os_variant") == "rhel7":
        return True
    return False


def vm_is_rhel6(self):
    """Extention to qemu.VM(virt_vm.BaseVM) class.
    """
    if self.params.get("os_variant") == "rhel6":
        return True
    return False


def vm_info(self, string, *args, **kwargs):
    """Extention to qemu.VM(virt_vm.BaseVM) class.
    """
    logger.info(self.name + " : " + string, *args, **kwargs)


def vm_error(self, string, *args, **kwargs):
    """Extention to qemu.VM(virt_vm.BaseVM) class.
    """
    logger.error(self.name + " : " + string, *args, **kwargs)


def extend_api_vm():
    """Extend qemu.VM(virt_vm.BaseVM) with useful methods.
    """
    qemu_vm.VM.is_linux = vm_is_linux
    qemu_vm.VM.is_win = vm_is_win
    qemu_vm.VM.is_rhel7 = vm_is_rhel7
    qemu_vm.VM.is_rhel6 = vm_is_rhel6
    qemu_vm.VM.info = vm_info
    qemu_vm.VM.error = vm_error


def type_variant(test, vm_name):
    vm = test.vms[vm_name]
    os_type = vm.params.get("os_type")
    os_variant = vm.params.get("os_variant")
    return (os_type, os_variant)


class SpiceUtilsError(Exception):
    """Exception raised in case the lib API fails."""


class SpiceUtilsUnknownVmType(SpiceUtilsError):
    """Unknow VM type."""

    def __init__(self, vm_name, *args, **kwargs):
        super(SpiceUtilsUnknownVmType, self).__init__(args, kwargs)
        self.vm_name = vm_name

    def __str__(self):
        return "Unkon VM type: %s" % self.vm_name


class SpiceUtilsBadVmType(SpiceUtilsError):
    """Bad VM type."""
    def __init__(self, vm_name, *args, **kwargs):
        super(SpiceUtilsBadVmType, self).__init__(args, kwargs)
        self.vm_name = vm_name

    def __str__(self):
        return "Bad and unexpected VM type: %s." % self.vm_name


# ..todo:: or aexpect.xxx ???
class SpiceUtilsCmdRun(SpiceUtilsError):
    """Fail to run cmd on VM."""
    def __init__(self, vm_name, cmd, output, *args, **kwargs):
        super(SpiceUtilsCmdRun, self).__init__(args, kwargs)
        self.vm_name = vm_name
        self.cmd = cmd
        self.output = output

    def __str__(self):
        return "Command: {0} failed at: {1} with output: {2}".format(
            self.cmd, self.vm_name, self.output)


class SpiceTestFail(exceptions.TestFail):
    """Unknow VM type."""

    def __init__(self, test, *args, **kwargs):
        super(Exception, self).__init__(args, kwargs)
        if test.cfg.pause_on_fail or test.cfg.pause_on_end:
            # 1 hour
            seconds = 60 * 60 * 10
            logger.error("Test %s has failed. Do nothing for %s seconds.",
                          test.cfg.id, seconds)
            time.sleep(seconds)


def finish_test(test):
    """Could be located at the end of the tests."""
    if test.cfg.pause_on_end:
        # 1 hour
        seconds = 60 * 60
        logger.info("Test %s is finished. Do nothing for %s seconds.",
                      test.cfg.id, seconds)
        time.sleep(seconds)


def is_yes(string):
    """Wrapper around util.strtobool.

    Parameters
    ----------
    string : str
        String to check.

    Note
    ----
    https://docs.python.org/2/distutils/apiref.html#distutils.util.strtobool
    True values are y, yes, t, true, on and 1; false values are n, no, f,
    false, off and 0. Raises ValueError if val is anything else.
    """
    return util.strtobool(str(string))


def str2res(res):
    """Convert resolution in str for: XXXxYYY to tuple.

    Parameters
    ----------
    res : str
        Resolution.

    Returns
    -------
    tuple
        Resolution.

    """
    width = int(res.split('x')[0])
    # The second split of - is a workaround because the xwinfo sometimes
    # prints out dashes after the resolution for some reason.
    height = int(res.split('x')[1].split('-')[0])
    return (width, height)


def res_gt(res1, res2):
    """Test res2 > res1

    Parameters
    ----------
    res1: tuple
        resolution
    res2: tuple
        resolution

    Returns
    -------
    bool
        res1 > res2

    """
    return h2 > h1 and w2 > w1


def res_eq(res1, res2):
    """Test res1 == res2

    Parameters
    ----------
    res1: tuple
        resolution
    res2: tuple
        resolution

    Returns
    -------
    bool
        res1 == res2

    """
    return res1 == res2


def is_eq(val, tgt, err_limit):
    """Test if val is equal to tgt in allowable limits.

    Parameters
    ----------
    val :
        Value to check.
    tgt :
        Specimen.
    err_limit :
        Acceptable percent change of x2 from x1.

    init: original integer value
    post: integer that must be within an acceptable percent of x1

    """
    if not isinstance(tgt, int):
        tgt = int(tgt)
    if not isinstance(post, int):
        val = int(val)
    if not isinstance(err_limit, int):
        err_limit = int(err_limit)
    sub = tgt * err_limit / 100
    bottom = tgt - sub
    up = tgt + sub
    ret =  bottom <= val and val <= up
    logger.info("Stating %d <= %d <= %d is %s.", bottom, val, up, str(ret))
    return ret


class Commands(object):
    """Class contains a set of actions to be performed on VM using SSH session.

    Derivative classes hold actions for specific OS version.
    """

    def __init__(self, test, vm_name):
        self.test = test
        self.cfg = test.cfg
        self.vm_name = vm_name
        self.vm = test.vms[vm_name]
        self.ssn = test.sessions[vm_name]
        self.assn = test.sessions_admin[vm_name]
        self.kvm = test.kvm[vm_name]
        self.os_type, self.os_variant = type_variant(test, vm_name)


    @staticmethod
    def get(test, vm_name):
        vm = test.vms[vm_name]
        os_type, os_variant = type_variant(test, vm_name)
        for cls in Commands.__subclasses__():
            if cls.is_for(os_type, os_variant):
                return cls(test, vm_name)
            if cls.is_for(os_type, None):
                return cls(test, vm_name)
        raise ValueError


    def __getattr__(self, name):
        """Notify user about unimplemented OS version.
        """
        if name in ["__getstate__", "__setstate__", "__slots__"]:
            raise AttributeError()
        raise NotImplementedError("%s for %s, %s", name, self.os_type,
                                  self.os_variant)


class CommandsWindows(Commands):

    @classmethod
    def is_for(cls, os_type, _):
        return os_type == 'windows'

    def __init__(self, *args, **kwargs):
        super(CommandsLinux, self).__init__(*args, **kwargs)


    def service_vdagent(self, action):
        """Start/Stop/... on the spice-vdagentd service.

        Parameters
        ----------
        action : str
            Action on vdagent-service: stop, start, restart, status, ...

            http://ss64.com/nt/net_service.html

            Know actions are: start / stop / pause / continue.

            .. todo:: Implement me. Not finished: status, restart.

        """
        cmd = 'net %s "RHEV Spice Agent"' % action
        self.ssn.cmd(cmd)


    def verify_virtio(self):
        """Verify Virtio-Serial linux driver is properly loaded.

        """
        cmd = self.cfg.pnputil + " /e"
        output = self.ssn.cmd(cmd)
        installed = "System devices" in output
        self.vm.info("Virtio Serial driver is installed:", installed)
        return installed


    def install_rv(self):
        """Install remote-viewer on a windows client.

        .. todo:: Add cfg.client_path_rv_dst = C:\virt-viewer

        """
        vm.copy_files_to(self.cfg.host_path, self.cfg.client_path_rv)
        cmd = r'start /wait msiexec /i %s INSTALLDIR="%s"' % (
            self.cfg.client_path_rv,
            self.cfg.client_path_rv_dst)
        self.ssn.cmd_output(cmd)


    def install_usbclerk_win(self):
        """Install usbclerk on a windows client.

        ..todo:: host_path - fix

        """
        vm.copy_files_to(self.cfg.host_path, self.cfg.client_path_usbc)
        cmd = "start /wait msiexec /i %s /qn" % self.cfg.client_path_usbc
        self.ssn.cmd_output(cmd)


    def reset_gui(self):
        """Kill remote-viewer.

        Raises
        ------
        SpiceUtilsError
            Fails to kill remote-viewer.

        """
        self.ssn = test.sessions[vm_name]
        # .. todo:: check if remote-viewer is running before killing it.
        cmd = r"taskkill /F /IM remote-viewer.exe"
        self.ssn.cmd(cmd)


    def kill_by_name(self, app_name):
        """Kill selected app on selected VM.

        Parameters
        ----------
        app_name : str
            Name of the binary.

        """
        cmd = "taskkill /F /IM %s" % app_name.split('\\')[-1]
        self.ssn.cmd(cmd)


class CommandsLinux(Commands):

    @classmethod
    def is_for(cls, os_type, _):
        return os_type == 'linux'


    def __init__(self, *args, **kwargs):
        super(CommandsLinux, self).__init__(*args, **kwargs)


    def service_vdagent(self, action):
        """Start/Stop/... on the spice-vdagentd service.

        Parameters
        ----------
        action : str
            Action on vdagent-service: stop, start, restart, status, ...

        """
        runner = remote.RemoteRunner(session=self.ssn)
        vdagentd = Factory.create_specific_service("spice-vdagentd",
                                                   run=runner.run)
        func = getattr(vdagentd, action)
        return func()


    def verify_vdagent(self):
        """Verifying vdagent is installed on a VM.

        """
        cmd = r"rpm -qa | grep spice-vdagent"
        self.ssn.cmd(cmd)


    def check_usb_policy(self):
        """Check USB policy in polkit file.

        Returns
        -------
        bool
            Status of grep command. If pattern is found 0 is returned. 0 in python
            is False so negative of grep is returned.

            .. todo: Move USB_POLICY_FILE to cfg.

        """
        cmd = 'grep "<allow_any>yes" %s' % USB_POLICY_FILE
        cmd_status = self.ssn.cmd_status(cmd)
        self.vm.info("USB policy is: %s.", cmd_status)
        return not cmd_status


    def add_usb_policy(self):
        """Add USB policy to policykit file.

        .. todo:: USB_POLICY_FILE_SRC, USB_POLICY_FILE to cfg

        """
        self.vm.info("Sending: %s.", USB_POLICY_FILE_SRC)
        vm.copy_files_to(USB_POLICY_FILE_SRC, USB_POLICY_FILE)


    @deco.retry(8, exceptions=(aexpect.ShellCmdError))
    def x_active(self):
        """Test if X session is active. Do nothing is X active. Othrerwise
        throw exception.
        """
        cmd = 'gnome-terminal -e /bin/true'
        self.ssn.cmd(cmd)
        self.vm.info("X session is present.")


    def _is_pid_alive(self, pid):
        """Verify the process is still alive.

        Parameters
        ----------
        pid : str
            Process that is to be checked.

        """
        cmd = "ps -p %s" % pid
        cmd_status = self.ssn.cmd_status(cmd)
        return not cmd_status


    # ..todo:: change function name.
    def str_input(self, string):
        """Sends string trough vm.send_key(). The string could be spice_password.

        Notes
        -----
        After string will be send Enter.

        Parameters
        ----------
        string : str
            Arbitrary string to be send to VM as keyboard events.

        """
        self.vm.info("Passing string '%s' as kbd events.", string)
        char_mapping = {":": "shift-semicolon",
                        ",": "comma",
                        ".": "dot",
                        "/": "slash",
                        "?": "shift-slash",
                        "=": "equal"}
        for character in string:
            if character in char_mapping:
                character = char_mapping[character]
            self.vm.send_key(character)
        # Enter
        self.vm.send_key("kp_enter")


    def print_rv_version(self):
        """Prints remote-viewer and spice-gtk version available inside.

        Parameters
        ----------
        rv_binary : str
            remote-viewer binary.

            if cfg.rv_ld_library_path:
                xxcmd = "LD_LIBRARY_PATH=/usr/local/lib %s" % cfg.rv_binary
            else:
                xxcmd = cfg.rv_binary
            try:
        """
        cmd = self.cfg.rv_binary + " -V"
        rv_ver = self.ssn.cmd(cmd)
        cmd = self.cfg.rv_binary + " --spice-gtk-version"
        spice_gtk_ver = self.ssn.cmd(cmd)
        self.vm.info("remote-viewer version: %s", rv_ver)
        self.vm.info("spice-gtk version: %s", spice_gtk_ver)

        #    except aexpect.ShellStatusError as ShellProcessTerminatedError:
        #        # Sometimes It fails with Status error, ingore it and continue.
        #        # It's not that important to have printed versions in the log.
        #        logger.debug(
        #            "Ignoring a Status Exception that occurs from calling print"
        #            "versions of remote-viewer or spice-gtk"
        #        )


    def verify_virtio(self):
        """Verify Virtio-Serial linux driver is properly loaded.

        """
        # cmd = "lsmod | grep virtio_console"
        cmd = "ls /dev/virtio-ports/"
        self.ssn.cmd(cmd)


    @deco.retry(8, exceptions=(AssertionError,))
    def x_turn_off(self):
        runner = remote.RemoteRunner(session=self.assn)
        srv_mng = service.Factory.create_service(run=runner.run)
        srv_mng.set_target("multi-user.target")  # pylint: disable=no-member
        xsession_flag_cmd = r"ss -x src '*X11-unix*' | grep -q -s 'X11'"
        active = not self.ssn.cmd_status(xsession_flag_cmd)
        assert active == False, "X is: on. But it should not."
        self.vm.info("X is: off.")


    @deco.retry(8, exceptions=(AssertionError,))
    def x_turn_on(self):
        runner = remote.RemoteRunner(session=self.assn)
        srv_mng = service.Factory.create_service(run=runner.run)
        srv_mng.set_target("graphical.target")  # pylint: disable=no-member
        xsession_flag_cmd = r"ss -x src '*X11-unix*' | grep -q -s 'X11'"
        active = not self.ssn.cmd_status(xsession_flag_cmd)
        assert active == True, "X is: off. But it should not."
        self.vm.info("X is: on.")


    def reset_gui(self):
        """Clears user GUI interface of a vm without restart.

        Restart graphical session at VM.

        Notes
        -----
            To accomplish this change SystemD/SystemV runlevels from graphical mode
            to multiuser mode, and back.


        Raises
        ------
        SpiceUtilsError
            Fails to restart Graphical session.

        """
        self.x_turn_off()
        self.x_turn_on()
        self.x_active()


    def export_x2ssh(self, var, fallback=None):
        """Take value from X session and export it to ssh session. Useful to
        export variables such as 'DBUS_SESSION_BUS_ADDRESS', 'AT_SPI_BUS'.

        Parameters
        ----------
        var : str
            Variable name.
        fallback : Optional[str]
            If value is absent in X session, then use this value.

        """
        val = self.get_x_var(var_name)
        if not val:
            val = fallback
        if val:
            self.vm.info("Export %s == %s", var_name, var_val)
            cmd = r"export %s='%s'" % (var_name, var_val)
            self.ssn.cmd(cmd)


    def install_rpm(self, rpm):
        """Install RPM package on a VM.

        Parameters
        ----------
        rpm : str
            Path to RPM to be installed. It could be path to .rpm file, or RPM
            name.
        """
        self.vm.info("Install RPM : %s.", rpm)
        pkg = rpm
        if rpm.endswith('.rpm'):
            pkg = rpm[:-4]
        cmd = 'rpm -q %s' % pkg
        status = self.ssn.cmd_status(cmd)
        if status == 0:
            self.vm.info("RPM %s is already installed.", pkg)
            return
        self.ssn.cmd("yum -y install %s" % rpm, timeout=500)


    def wait_for_win(self, pattern, prop="_NET_WM_NAME"):
        """Wait until active window has "pattern" in window name.

        ..todo:: Write same function for MS Windows.

        Info
        ----
        http://superuser.com/questions/382616/detecting-currently-active-window

        Parameters
        ----------
        pattern : str
            Pattern for window name.

        Raises
        ------
        SpiceUtilsError
            Timeout and no window was found.

        """
        cmd = r"xprop -notype -id " \
            r"$(xprop -root 32x '\t$0' _NET_ACTIVE_WINDOW | cut -f 2) "
        cmd += prop

        @deco.retry(8, exceptions=(SpiceUtilsError, aexpect.ShellCmdError))
        def is_active():
            self.vm.info("Test if window is active: %s", pattern)
            output = self.ssn.cmd(cmd)
            self.vm.info("Current win name: %s", output)
            if pattern not in output:
                msg = "Can't find active window with pattern %s." % pattern
                raise SpiceUtilsError(msg)
            self.vm.info("Found active window: %s.", pattern)

        is_active()


    def deploy_epel_repo(self):
        """Deploy epel repository to RHEL VM.

        """
        # Check existence of epel repository
        cmd = ("if [ ! -f /etc/yum.repos.d/epel.repo ]; then echo"
            " \"NeedsInstall\"; fi")
        output = self.ssn.cmd(cmd)
        # Install epel repository If needed
        if "NeedsInstall" in output:
            arch = self.ssn.cmd("arch")
            if "i686" in arch:
                arch = "i386"
            else:
                arch = arch[:-1]
            if "release 5" in self.ssn.cmd("cat /etc/redhat-release"):
                cmd = ("yum -y localinstall http://download.fedoraproject.org/"
                    "pub/epel/5/%s/epel-release-5-4.noarch.rpm 2>&1" % arch)
                self.vm.info("Installing epel repository to %s", self.cfg.guest_vm)
                self.ssn.cmd(cmd)
            elif "release 6" in self.ssn.cmd("cat /etc/redhat-release"):
                cmd = ("yum -y localinstall http://download.fedoraproject.org/"
                    "pub/epel/6/%s/epel-release-6-8.noarch.rpm 2>&1" % arch)
                self.vm.info("Installing epel repository to %s", self.cfg.guest_vm)
                self.ssn.cmd(cmd)
            else:
                raise Exception("Unsupported RHEL guest")


    def set_resolution(self, res, display):
        """Sets resolution of qxl device on a VM.

        Parameters
        ----------
        res : str
            Resolution.
        display : str
            Target display.

        """
        self.vm.info("Seeting resolution to %s.", res)
        cmd = "xrandr --output %s --mode %s " % (display, res)
        self.ssn.cmd(cmd)


    def get_connected_displays(self):
        """Get list of video devices on a VM.

        Return
        ------
            List of active displays on the VM.

        """
        cmd = "xrandr | grep -E '[[:space:]]connected[[:space:]]'"
        raw = self.ssn.cmd_output(cmd)
        displays = [a.split()[0] for a in raw.split('n') if a is not '']
        return displays


    def get_display_resolution(self):
        """Returns list of resolutions on all displays of a VM.

        Return
        ------
            List of resolutions.
        """
        cmd = "xrandr | grep '*'"
        raw = self.ssn.cmd_output(cmd)
        res = [a.split()[0] for a in raw.split('\n') if a is not '']
        return res


    def get_open_window_ids(fltr):
        """Get X server window ids of active windows matching filter.

        Parameters
        ----------
        fltr: str.
            Name of binary/title.

        Return
        ------
            List of active windows matching filter.

        """
        xwininfo = self.ssn.cmd_output("xwininfo -tree -root")
        ids = [a.split()[0] for a in xwininfo.split('\n') if fltr in a]
        windows = []
        for window in ids:
            out = subprocess.check_output('xprop -id %s' % window, shell=True)
            for line in out.split('\n'):
                if ('NET_WM_WINDOW_TYPE' in line and
                        'ET_WM_WINDOW_TYPE_NORMAL' in line):
                    windows.append(window)
        return windows


    def get_window_props(win_id):
        """Get full properties of a window with speficied ID.

        Parameters
        ----------
        win_id : str
            X server id of a window.

        Return
        ------
            Returns output of xprop -id.

        """
        cmd = "xprop -id %s" % win_id
        raw = self.ssn.cmd_output(cmd)
        return raw


    def get_wininfo(self, win_id):
        """Get xwininfo for windows of a specified ID.

        Return
        ------
            Output xwininfo -id %id on the session.

        """
        cmd = "xwininfo -id %s" % win_id
        raw = self.ssn.cmd_output(cmd)
        return raw


    def get_window_geometry(self, win_id):
        """Get resolution of a window.

        Parameters
        ----------
        win_id : str
            ID of the window of interest.

        Return
        ------
            WidthxHeight of the selected window.

        """
        xwininfo = self.get_wininfo(win_id)
        for line in xwininfo:
            if '-geometry' in line:
                return re.split(r'[\+\-\W]', line)[1]  # ..todo: review


    def kill_by_name(self, app_name):
        """Kill selected app on selected VM.

        Parameters
        ----------
        app_name : str
            Name of the binary.
        XXX
        """
        try:
            cmd = "pkill %s" % app_name.split(os.path.sep)[-1]
            output = self.ssn.cmd_output(cmd)
        except aexpect.ShellCmdError:
            if output == 1:
                pass
            else:
                raise SpiceUtilsError("Cannot kill it.")


    def is_fullscreen_xprop(self, win_name, window=0):
        """Tests if remote-viewer windows is fullscreen based on xprop.

        Parameters
        ----------
        win_name : str
            Window name.
        window : int
            Which window is tested (0-3).

        Returns
        -------
        Returns True if fullscreen property is set.

        """
        win_id = self.get_open_window_ids(win_name)[window]
        props = self.get_window_props(win_id)
        for prop in props.split('\n'):
            if ('_NET_WM_STATE(ATOM)' in prop and
                    '_NET_WM_STATE_FULLSCREEN ' in prop):
                return True


    def window_resolution(self, in_name, window=0):
        """ ..todo:: write me
        """
        win_id = self.get_open_window_ids(win_name)[window]
        return self.get_window_geometry(win_id)


    def get_res(self):
        """Gets the resolution of a VM

        XXX ? MONITOR # ?

        Return
        ------

        """
        cmd = "xrandr -d :0 2> /dev/null | grep '*'"
        guest_res_raw = self.ssn.cmd_output(cmd)
        guest_res = guest_res_raw.split()[0]
        return guest_res

    # ..todo:: implement
    # def get_fullscreen_windows(test):
    #    cfg = test.cfg
    #    windows = self.get_windows_ids()

    def get_corners(self, win_title):
        """Gets the coordinates of the 4 corners of the window.

        Info
        ----
        http://www.x.org/archive/X11R6.8.0/doc/X.7.html#sect6

        Parameters
        ----------
        win_title : str
            XXX.

        Return
        ------
        list
            Corners in format: [('+470', '+187'), ('-232', '+187'),
                                ('-232', '-13'), ('+470', '-13')]

        """
        rv_xinfo_cmd = "xwininfo -name %s" % win_title
        rv_xinfo_cmd += " | grep Corners"
        # Expected format:   Corners:  +470+187  -232+187  -232-13  +470-13
        raw_out = client_session.cmd(rv_xinfo_cmd)
        line = raw_out.strip()
        corners = [tuple(re.findall("[+-]\d+",i)) for i in line.split()[1:]]
        return corners


    def get_geom(self, win_title):
        """Gets the geometry of the rv_window.

        Parameters
        ----------
        win_title : str
            XXX.

        Returns
        -------
        tuple
            Geometry of RV window. (x,y)

        """
        xinfo_cmd = "xwininfo -name %s" % win_title
        xinfo_cmd += " | grep geometry"
        # Expected '  -geometry 898x700+470-13'
        res_raw = ssn.cmd(rv_xinfo_cmd)
        res = re.findall('\d+x\d+', res_raw)[0]
        self.vm.info("Window %s has geometry: %s", win_title, res)
        return str2res(rv_res)


    def get_x_var(self, var_name):
        """Gets the env variable value by its name from X session.

        Info
        ----
        It is no straight way to get variable value from X session. If you try to
        read var value from SSH session it could be different from X session var or
        absent. The strategy used in this function is:

            1. Run terminal. Terminal will be disconnected from SSH session. The
            parent of the terminal will be X manager. Terminal inherits variables
            from X manager.  Dump variables to file.
            2. Read the file for interested variable.

        Parameters
        ----------
        var_name : str
            Spice test object.

        Returns
        -------
        str
            Env variable value.

        """
        terminal = 'gnome-terminal'
        dump_file = tempfile.mktemp()
        dump_env_cmd = """'sh -c "export -p > %s"'""" % dump_file
        cmd1 = terminal + " -e " + dump_env_cmd
        cmd2 = r'cat "%s"' % dump_file
        pattern = "\s%s=.+" % var_name
        self.ssn.cmd(cmd1)
        env = self.ssn.cmd(cmd2)
        ret = re.findall(pattern, env)
        if ret:
            ret = ret[0]
            ret = ret.strip()
            ret = ret.split('=', 1)[1]
        else:
            ret = ""
        self.vm.info("var %s = %s", var_name, ret)
        return ret


class CommandsLinuxRhel7(Commands):

    @classmethod
    def is_for(cls, os_type, os_variant):
        return os_type == 'linux' and os_variant == 'rhel7'

    def __init__(self, *args, **kwargs):
        super(CommandsLinux, self).__init__(*args, **kwargs)


    def turn_accessibility(self, on=True):
        """Turn accessibility on vm.

        Parameters
        ----------
        on : str
            Spice test object.

        """
        if is_yes(on):
            val = 'true'
        else:
            val = 'false'
        cmd = "gsettings set org.gnome.desktop.interface toolkit-accessibility %s" % val
        self.ssn.cmd(cmd)


class CommandsLinuxRhel6(Commands):

    @classmethod
    def is_for(cls, os_type, os_variant):
        return os_type == 'linux' and os_variant == 'rhel6'

    def __init__(self, *args, **kwargs):
        super(CommandsLinux, self).__init__(*args, **kwargs)

    def turn_accessibility(self, on=True):
        """Turn accessibility on vm.

        Parameters
        ----------
        on : str
            Spice test object.

        """
        if is_yes(on):
            val = 'true'
        else:
            val = 'false'
        # gconftool-2 --get "/desktop/gnome/interface/accessibility"
        # temporarily (for a single session) enable Accessibility:
        # GNOME_ACCESSIBILITY=1
        # session.cmd("gconftool-2 --shutdown")
        cmd = "gconftool-2 --set /desktop/gnome/interface/accessibility --type bool %s" % val
        self.ssn.cmd(cmd)
