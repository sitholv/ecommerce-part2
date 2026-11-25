/* The unenhanced page keeps every navigation link visible. */
const button = document.querySelector('.menu-toggle');
const navigation = document.querySelector('#navigation');
if (button && navigation) {
  document.documentElement.classList.add('js-nav');
  const narrow = matchMedia('(max-width: 1100px)');
  const reset = () => {
    button.hidden = !narrow.matches;
    navigation.classList.remove('open');
    button.setAttribute('aria-expanded', 'false');
  };
  button.addEventListener('click', () => {
    button.setAttribute('aria-expanded', String(navigation.classList.toggle('open')));
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && navigation.classList.contains('open')) {
      reset();
      button.focus();
    }
  });
  narrow.addEventListener('change', reset);
  reset();
}
