/**
 * 管理页装配。
 *
 * 四个面板各自管理自己的监听与取数，这里只负责一起挂、一起卸。
 * 之所以不做成一个大模块：成员/项目属于工作区治理，运维区属于数据生命周期，
 * 账号安全是「关于我自己」—— 三者的读者、权限和变更频率都不一样，
 * 放一个文件里迟早会长回 500 行。
 */

import { mountMembers, unmountMembers, load as loadMembers } from './members.js';
import { mountProjects, unmountProjects, load as loadProjects } from './projects.js';
import { mountOperations, unmountOperations, load as loadOperations } from './operations.js';
import { mountAccount, unmountAccount, load as loadAccount } from './account.js';

let mounted = false;

export function mountAdminView() {
  if (mounted) return;
  mounted = true;
  mountMembers();
  mountProjects();
  mountOperations();
  mountAccount();
}

export function unmountAdminView() {
  if (!mounted) return;
  mounted = false;
  unmountMembers();
  unmountProjects();
  unmountOperations();
  unmountAccount();
}

/**
 * 重新拉取全部面板。
 * 供工具栏刷新按钮与「改完东西回到本页」的场景使用。
 */
export function reloadAdmin() {
  void loadMembers();
  void loadProjects();
  loadOperations();
  loadAccount();
}
