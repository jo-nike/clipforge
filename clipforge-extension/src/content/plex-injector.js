class PlexButtonInjector {
  constructor() {
    this.container = null;
    this.prevButton = null;
    this.nextButton = null;
    this.injected = false;
    this.observer = null;
  }

  async inject() {
    if (this.injected) return true;

    const targetElement = await this.findTargetElement();
    if (!targetElement) {
      console.log('ClipForge: Could not find target element for button injection');
      return false;
    }

    this.createButtons();
    this.insertButtons(targetElement);
    this.injected = true;
    this.observeForRemoval();

    return true;
  }

  async findTargetElement() {
    const selectors = [
      '[aria-label="Player Controls"] button[aria-label="Close"]',
      '[data-testid="closeButton"]',
      '.PlayerControls-buttonGroup button:last-child',
      '[class*="PlayerControls"] button[class*="close"]',
      'button[title="Close"]'
    ];

    for (let i = 0; i < 30; i++) {
      for (const selector of selectors) {
        const element = document.querySelector(selector);
        if (element) {
          return element.parentElement;
        }
      }
      await new Promise(resolve => setTimeout(resolve, 500));
    }

    const fallbackContainer = document.querySelector('[aria-label="Player Controls"], [class*="PlayerControls"]');
    return fallbackContainer;
  }

  createButtons() {
    this.container = document.createElement('div');
    this.container.className = 'clipforge-button-container';
    this.container.style.cssText = 'display: inline-flex; margin: 0 8px;';

    this.prevButton = this.createButton('previous', '[-30s]', 'Create clip from last 30 seconds');
    this.nextButton = this.createButton('next', '[+30s]', 'Create clip for next 30 seconds');

    this.container.appendChild(this.prevButton);
    this.container.appendChild(this.nextButton);
  }

  createButton(direction, text, tooltip) {
    const button = document.createElement('button');
    button.className = 'clipforge-button';
    button.setAttribute('data-direction', direction);
    button.setAttribute('title', tooltip);
    button.setAttribute('aria-label', tooltip);
    
    const iconSpan = document.createElement('span');
    iconSpan.className = 'clipforge-button-icon';
    iconSpan.textContent = text;
    
    button.appendChild(iconSpan);

    button.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      this.handleButtonClick(direction, button);
    });

    return button;
  }

  insertButtons(targetElement) {
    const closeButton = targetElement.querySelector('[aria-label="Close"], [data-testid="closeButton"], button:last-child');
    
    if (closeButton && closeButton.nextSibling) {
      targetElement.insertBefore(this.container, closeButton.nextSibling);
    } else if (closeButton) {
      targetElement.insertBefore(this.container, closeButton);
    } else {
      targetElement.appendChild(this.container);
    }
  }

  handleButtonClick(direction, button) {
    const event = new CustomEvent('clipforge-create-clip', {
      detail: { direction }
    });
    document.dispatchEvent(event);

    this.showFeedback(button, 'pending');
  }

  showFeedback(button, status) {
    const originalContent = button.innerHTML;
    button.disabled = true;

    switch (status) {
      case 'pending':
        button.classList.add('clipforge-pending');
        button.querySelector('.clipforge-button-icon').textContent = '...';
        break;
      case 'success':
        button.classList.remove('clipforge-pending');
        button.classList.add('clipforge-success');
        button.querySelector('.clipforge-button-icon').textContent = '✓';
        break;
      case 'error':
        button.classList.remove('clipforge-pending');
        button.classList.add('clipforge-error');
        button.querySelector('.clipforge-button-icon').textContent = '✗';
        break;
    }

    if (status !== 'pending') {
      setTimeout(() => {
        button.innerHTML = originalContent;
        button.classList.remove('clipforge-success', 'clipforge-error', 'clipforge-pending');
        button.disabled = false;
      }, 2000);
    }
  }

  updateButtonStatus(direction, status) {
    const button = direction === 'previous' ? this.prevButton : this.nextButton;
    if (button) {
      this.showFeedback(button, status);
    }
  }

  observeForRemoval() {
    this.observer = new MutationObserver(() => {
      if (!document.body.contains(this.container)) {
        this.injected = false;
        this.inject();
      }
    });

    this.observer.observe(document.body, {
      childList: true,
      subtree: true
    });
  }

  updateSettings(settings) {
    if (settings.clipDuration) {
      const duration = settings.clipDuration;
      if (this.prevButton) {
        this.prevButton.querySelector('.clipforge-button-icon').textContent = `[-${duration}s]`;
        this.prevButton.setAttribute('title', `Create clip from last ${duration} seconds`);
      }
      if (this.nextButton) {
        this.nextButton.querySelector('.clipforge-button-icon').textContent = `[+${duration}s]`;
        this.nextButton.setAttribute('title', `Create clip for next ${duration} seconds`);
      }
    }
  }

  destroy() {
    if (this.observer) {
      this.observer.disconnect();
    }
    if (this.container && this.container.parentNode) {
      this.container.parentNode.removeChild(this.container);
    }
    this.injected = false;
  }
}

export default PlexButtonInjector;