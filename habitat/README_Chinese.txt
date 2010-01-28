= 欢迎使用 Habitat 个人资讯管理平台 =

<toc>
== # 什么是Habitat ==

Habitat是一个小巧、快捷、安装简便、可扩展性强的个人资讯管理平台。
Habitat使用perl语言编写，以sqlite本地数据库作为后端，并包含了内置
的服务器脚本。Habitat可以直接在本地计算机上运行使用，也可以放置在
开放服务器上提供多人或者社区使用。

Habitat是一个wiki引擎，也同时是一个内容管理系统(CMS)。用户可以
使用Habitat来快速建立和维护个人网站，或者为社区提供协作式创作平台。

Habitat是由[http://nmr.mgh.harvard.edu/~fangq/ 房骞骞]在开源中文
字体项目[http://wenq.org 文泉驿]长期使用的wiki引擎的基础上改写
而成。新添加的功能包括用户管理系统、后台数据库功能、多层次wiki页面、
多语言支持、面向对象的wiki数据结构以及可编程的扩展接口。

== # 如何安装Habitat ==

Habitat有四种运行模式：标准模式，扩展模式，精简模式，最小模式。
其中在最小模式下，您甚至可以仅仅使用一个200kB的脚本来实现
大多数功能。

使用标准模式来运行Habitat是推荐的做法。在这种模式下，您可以使用
sqlite来作为数据库后台引擎，这样不但可以节省大量的磁盘空间，而且
方便检索和备份。标准模式要求perl支持以下的模块：
 DBI, DBD::Sqlite3, Text::Diff, Text::Patch, Crypt::DES
如果您使用Ubuntu Linux，您可以通过下面的命令安装所有依赖软件：
  sudo apt-get install perl python sqlite3 libdbd-sqlite3-perl \
     libtext-diff-perl libtext-patch-perl libcrypt-des-perl
其中perl和python在大多数情况下已经安装，所以上面的命令只需要
增加大约1MB的系统空间。如果您没有系统管理员权限，您可以从Habitat
的网站上直接下载编译好的perl模块，并放在lib子目录下。

安装完成后您需要初始化数据库：
  sqlite3 db/habitatdb.db '.read db/gendb.sql'
为安全性考虑，我们强烈建议您重新设定管理员密码和网站Hash，您需要编辑config文件
  nano habitatdb/config
查找<tt>AdminPass</tt>和<tt>CaptchaKey</tt>，并把其中的字符串换成您希望使用
的密码。其中<tt>CaptchaKey</tt>的值只能包含0123456789以及ABCDEF。
为了保护您的密码不被其他用户看到，请将<tt>habitatdb</tt>目录移到一个www用户
无法访问的目录下，比如<tt>/var/lib/habitatdb</tt>下面(您需要创建这个目录)。
您需要同时将index.cgi脚本中<tt>DataDir</tt>变量对应的值设置为新目录的名字。

完成设置后，您就可以测试运行Habitat了。您只需要在控制台
运行<tt>runlocal.sh</tt>脚本即可。一个浏览器窗口将自动弹出，Habitat
将自动载入首页页面。如果您希望使用中文作为默认语言，请在
index.cgi文件中找到<tt>LangID="en"</tt>并将en替换为cn。

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
基本语法。请查看[Local:HabitatTest HabitatTest]页面
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
多媒体数据(包括音频、视频和手势等)的软件。Habitat遵循HUC原则的
一个模板软件：它本身是由高级脚本语言写成，它处理的对象是可以
直接理解的纯文本数据。

我们欢迎大家开发更多遵循HUC原则的软件。我们认为更多HUC软件将
对未来的计算机发展以及建立一个透明、开放的用户、软件生态系统有
着积极的作用。
