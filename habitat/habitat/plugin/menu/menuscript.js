function createcssmenu(){
  var submenu="wikiullevel2";
  var offset=-1;
    var ultags=document.getElementsByTagName("ul");
    for (var t=0; t<ultags.length; t++){
        if(ultags[t].className!=submenu) continue;
	ultags[t].style.top=ultags[t].parentNode.offsetHeight+offset+"px"
    	ultags[t].parentNode.onmouseover=function(){
		this.style.zIndex=100
	   	this.getElementsByTagName("ul")[0].style.visibility="visible"
		this.getElementsByTagName("ul")[0].style.zIndex=0
    	}
    	ultags[t].parentNode.onmouseout=function(){
		this.style.zIndex=0
		this.getElementsByTagName("ul")[0].style.visibility="hidden"
		this.getElementsByTagName("ul")[0].style.zIndex=100
    	}
    }
}
if (window.addEventListener)
  window.addEventListener("load", createcssmenu, false);
else if (window.attachEvent)
  window.attachEvent("onload", createcssmenu);
else if(document.addEventListener)
  document.addEventListener("load", createcssmenu, false);
