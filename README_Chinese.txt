= 欢迎使用 Habitat 个人资讯管理平台 =
{{atom/menu/HabitatMenu}}
<toc>
== # 什么是Habitat ==

Habitat是一个小巧、快捷、安装简便、可扩展性强的个人资讯管理平台。
Habitat使用perl语言编写，以sqlite本地数据库作为后端，并包含了内置
的服务器脚本。Habitat可以直接在本地计算机上运行使用，也可以放置在
开放服务器上提供多人或者社区使用。

Habitat是一个wiki引擎，也同时是一个内容管理系统(CMS)。用户可以
使用Habitat来快速建立和维护个人网站，或者为社区提供协作式创作平台。

Habitat是由[http://nmr.mgh.harvard.edu/~fangq/ 房骞骞]在
[http://www.usemod.com/cgi-bin/wiki.pl UseModWiki]的基础上
为开源中文字体项目[http://wenq.org 文泉驿]开发并优化的。
新添加的功能包括用户管理系统、后台数据库功能、多层次wiki页面、
多语言支持、面向对象的wiki数据结构以及可编程的扩展接口。

{(Habitat/Download)}

== # 如何使用Habitat ==

第一次使用Habitat，请使用左侧的[http:?action=newlogin Register(注册帐号)]链接来设定用户
名，密码和管理员口令。如果您不设定用户名，所有编辑将显示您的IP地址。

如果您希望设定自己为Habitat上唯一有编辑权的用户(其他用户只可以阅读)，
您需要在注册页面中输入前面设定好的管理员口令并保存，然后在<tt>config</tt>文件中把
<tt>EditAllowed</tt>选择设置为0，否则任何用户都可以编辑。对于个人网站，我们
建议用户使用上述设置。

添加、改写页面内容，请选择页面上面的"编辑本页"链接。Habitat遵循最为
广泛使用的wiki排版格式语言，兼容[http://www.usemod.com/cgi-bin/wiki.pl?TextFormattingRules UseModWiki] 
以及大多数[http://en.wikipedia.org/wiki/Help:Wiki_markup Wikipedia]
基本语法。请查看[Local:HabitatTest HabitatTest]和[Local:HabitatNewTest HabitatNewTest]页面
获取更多排版格式信息。

Habitat支持多层次Wiki页面命名。您可以建立诸如"[[页面/子页面]]"
和"[[页面/子页面/底层页面]]"形式的页面结构来保存树状结构的信息。

== # 如何获取帮助或参与开发 ==

您可以访问[http://wenq.org/forum/viewforum.php?f=8 Habitat的论坛]
来获取更多帮助信息。我们也会在[http://wenq.org/habitat/ 项目主页]
上公布更新公告。

Habitat是一个开源项目。您可以帮助我们改进代码、添加新的插件、设计皮肤
和样式、测试并反馈bug。请访问[http://wenq.org/habitat/ Habitat项目主页]
并加入开发者行列。

== # 更大的计划 ==

Habitat项目是“可理解计算(HUC)”的一个子项目。HUC项目的目的是推动
开放、安全、合作以及直观的计算模型和软件。目前，HUC项目重点
开发一系列以脚本语言为基础，处理可被人类理解的文字、图案以及
多媒体数据(包括音频、视频和手势等)的软件。Habitat是遵循HUC原则的
一个模板软件：它本身是由高级脚本语言写成，它处理的对象是可以
直接理解的纯文本数据。

我们欢迎大家开发更多遵循HUC原则的软件。我们认为更多HUC软件将
对未来的计算机发展以及建立一个透明、开放的用户、软件生态系统有
着积极的作用。
