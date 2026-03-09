"""
E-MailRelay 路徑組態

集中管理 E-MailRelay 安裝路徑，所有路徑由安裝目錄動態衍生。
安裝目錄可透過 SystemSetting 的 emailrelay_install_dir 設定。
"""
import os

DEFAULT_INSTALL_DIR = '/opt/E-MailRelay'


def get_install_dir():
    """取得 E-MailRelay 安裝目錄"""
    try:
        from ..models.system_setting import SystemSetting
        return SystemSetting.get('emailrelay_install_dir', DEFAULT_INSTALL_DIR)
    except Exception:
        return DEFAULT_INSTALL_DIR


def get_paths():
    """
    取得所有 E-MailRelay 相關路徑

    Returns:
        dict: install_dir, submit_bin, server_bin, spool_dir,
              auth_file, conf_file, log_dir
    """
    install_dir = get_install_dir()
    return {
        'install_dir': install_dir,
        'submit_bin': os.path.join(install_dir, 'sbin', 'emailrelay-submit'),
        'server_bin': os.path.join(install_dir, 'sbin', 'emailrelay'),
        'spool_dir': os.path.join(install_dir, 'spool'),
        'auth_file': os.path.join(install_dir, 'etc', 'emailrelay.auth'),
        'conf_file': os.path.join(install_dir, 'etc', 'emailrelay.conf'),
        'log_dir': os.path.join(install_dir, 'logs'),
    }


def validate_install_dir(install_dir):
    """
    驗證安裝目錄是否包含有效的 E-MailRelay 安裝

    Returns:
        tuple: (is_valid: bool, errors: list[str])
    """
    errors = []

    if not os.path.isdir(install_dir):
        errors.append(f'目錄不存在: {install_dir}')
        return False, errors

    submit_bin = os.path.join(install_dir, 'sbin', 'emailrelay-submit')
    server_bin = os.path.join(install_dir, 'sbin', 'emailrelay')
    spool_dir = os.path.join(install_dir, 'spool')

    if not os.path.isfile(submit_bin):
        errors.append(f'找不到 emailrelay-submit: {submit_bin}')

    if not os.path.isfile(server_bin):
        errors.append(f'找不到 emailrelay: {server_bin}')

    if not os.path.isdir(spool_dir):
        errors.append(f'Spool 目錄不存在: {spool_dir}')
    elif not os.access(spool_dir, os.W_OK):
        errors.append(f'Spool 目錄無寫入權限: {spool_dir}')

    return len(errors) == 0, errors
