document.addEventListener('DOMContentLoaded', () => {
  const mainNav = document.querySelector('.main-nav');
  const goTop = document.querySelector('#goTop');

  // combine scroll event
  // for nav stick class
  // for top bar 
  window.addEventListener('scroll', () => {
    const scrollTop = document.documentElement.scrollTop || document.body.scrollTop;

    // 处理导航栏 sticky 类
    if (scrollTop > 60) {
      mainNav.classList.add('sticky');
    } else {
      mainNav.classList.remove('sticky');
    }

    // 处理返回顶部按钮的 active 类
    if (scrollTop > 300) {
      goTop.classList.add('active');
    } else {
      goTop.classList.remove('active');
    }
  });

  // 触发一次 scroll 事件以初始化状态
  window.dispatchEvent(new Event('scroll'));

  // 返回顶部按钮点击事件
  goTop.addEventListener('click', (e) => {
    e.preventDefault(); // 阻止默认行为（如 <a> 标签的跳转）
    window.scrollTo({
      top: 0,
      behavior: 'smooth'
    });
  });
});