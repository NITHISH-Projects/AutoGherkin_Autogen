# Author: MARRI NITHISH
from bs4 import BeautifulSoup
from autogherkin_autogen.config import config

class DOMParser:
    def __init__(self, page_source):
        self.soup = BeautifulSoup(page_source, 'html.parser')
        self.max_elements = config['analysis']['max_elements']

    def parse_hoverable_elements(self):
        """Parse static DOM for potential hover structures like nested lists for menus."""
        potential_elements = []
        # Find navigation menus, dropdowns
        navs = self.soup.find_all(['nav', 'ul', 'div'], class_=['dropdown', 'menu', 'nav'])
        for nav in navs:
            links = nav.find_all('a', limit=self.max_elements)
            if links:
                potential_elements.append({
                    'type': 'menu',
                    'elements': [{'tag': a.name, 'text': a.get_text(strip=True)[:50], 'href': a.get('href')} for a in links]
                })
        # Find images or buttons that might have overlays
        imgs = self.soup.find_all('img', limit=self.max_elements)
        for img in imgs:
            potential_elements.append({
                'type': 'image_overlay',
                'element': {'tag': 'img', 'src': img.get('src'), 'alt': img.get('alt')}
            })
        return potential_elements

    def extract_interactive_elements(self):
        """Extract interactive elements like buttons, links."""
        interactives = self.soup.find_all(['a', 'button', 'input'], limit=self.max_elements)
        return [{'tag': el.name, 'text': el.get_text(strip=True)[:50], 'attributes': dict(el.attrs)} for el in interactives]
