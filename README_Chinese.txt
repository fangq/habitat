= 欢迎使用 Habitat =
<toc>

Habitat 是一个用 Perl 编写的小巧、快速的 wiki 引擎。把它放到任何能运行 Perl 的网站服务器上，您和合作者就可以直接在浏览器里共同编辑网站，每一次修改都会保存在页面历史中。

'''这是一个内置页面。'''新建的 Habitat wiki 在有人编辑之前都会显示这个页面。登录后点击“编辑本页”即可换成您自己的首页。

== # Habitat 的功能 ==

* '''wiki 编辑：'''简单的文本标记（[[Habitat/Markup|标记语法]]，英文），每个页面都有完整的修订历史和差异比较，另有[http:?action=rc 最近更新]、RSS 订阅和全文搜索。
* '''树状页面：'''像 <tt>项目/笔记/2026</tt> 这样的名字就是子页面；<tt><nowiki><localtree></nowiki></tt> 标记列出当前页面下的所有子页面。
* '''一处编写，多处复用：'''<tt><nowiki>{{页面}}</nowiki></tt> 嵌入另一个页面的显示结果，<tt><nowiki>{(页面)}</nowiki></tt> 嵌入它的原始文本。
* '''页面规则：'''页面可以带有文本替换规则，并自动作用于它的所有子页面，从而把 wiki 的一部分变成缺陷跟踪、术语表或幻灯片。详见 [[Habitat/NewSyntax|高级功能]]（英文）。
* '''Markdown：'''第一行为 <tt><nowiki><!-- markdown --></nowiki></tt> 的页面用 Markdown 书写。
* '''博客和论坛：'''一行 <tt><nowiki><board></nowiki></tt> 就能把页面变成博客或讨论区。每篇帖子和每条回复都是独立的页面，支持分页、标签、置顶、关闭主题和版主管理。
* '''帐号和权限：'''可以开放注册，也可以只允许持有编辑或管理员口令的人注册；用户可以通过邮件重设密码；页面可以单独限制阅读、编辑或锁定。
* '''默认安全：'''密码用 bcrypt 保存，所有表单都有 CSRF 保护，登录有频率限制；用户输入的 HTML 会被过滤，只有管理员最后保存的页面才能包含脚本。
* '''几乎处处可运行：'''普通 CGI 虚拟主机、PSGI（Starman、plackup）、mod_perl 或 FastCGI 均可；数据可存放在 SQLite（默认）、MariaDB/MySQL 或 PostgreSQL；静态页面缓存让 Apache 无需启动 Perl 即可为匿名访客提供页面。
* '''中英文界面'''（[http:?action=browse&id=Home&lang=en English]）。

== # 快速上手 ==

# '''注册帐号：'''点击页面上方的[http:?action=newlogin 注册]。如果本站只接受受邀注册，您需要向站长索取编辑或管理员口令；同时填写管理员口令会使您的帐号成为管理员。
# '''编辑页面：'''点击“编辑本页”，修改文字后保存。任何内容都不会丢失：“查看其它版本”可以找回以前的每一个版本。
# '''新建页面：'''在任意页面写一个链接，例如 <tt><nowiki>[[我的新页面]]</nowiki></tt>，保存后点击该链接即可开始编写新页面。
# '''学习标记语法'''请看 [[Habitat/Markup]]，'''高级功能'''请看 [[Habitat/NewSyntax]]（均为英文）。
# '''架设自己的 wiki''' 请参照 [[Habitat/Install]]（英文）。

== # 源代码与帮助 ==

* 源代码、版本发布和问题反馈：https://github.com/fangq/habitat
* 项目主页：https://wenq.org/habitat/
* 许可证：GNU 通用公共许可证（GPL）第 2 版或更新版本。

Habitat 于 2006 年起源于开源字体项目[https://wenq.org/ 文泉驿]的 wiki，由[https://github.com/fangq 房骞骞]在 [https://www.usemod.com/cgi-bin/wiki.pl UseModWiki] 的基础上开发，并于 2026 年针对安全、速度和现代服务器进行了全面改写。
