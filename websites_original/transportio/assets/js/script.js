'use strict';



/**
 * navbar toggle
 */

const navbar = document.querySelector("[data-navbar]");
const navToggler = document.querySelectorAll("[data-nav-toggler]");
const navLinks = document.querySelectorAll("[data-nav-link]");
const overlay = document.querySelector("[data-overlay]");

const toggleNavbar = () => {
  navbar.classList.toggle("active");
  overlay.classList.toggle("active");
};

const closeNavbar = () => {
  navbar.classList.remove("active");
  overlay.classList.remove("active");
};

navToggler.forEach(toggler => {
  toggler.addEventListener("click", toggleNavbar);
});

navLinks.forEach(link => {
  link.addEventListener("click", closeNavbar);
});


/**
 * header
 */

const header = document.querySelector("[data-header]");
const backTopBtn = document.querySelector("[data-back-top-btn]");

window.addEventListener("scroll", function () {
  if (window.scrollY >= 100) {
    header.classList.add("active");
    backTopBtn.classList.add("active");
  } else {
    header.classList.remove("active");
    backTopBtn.classList.remove("active");
  }
});