import asyncio
import aiohttp
import os
from crawl4ai import AsyncWebCrawler
from urllib.parse import urljoin, urlparse, unquote
import logging
import json
from datetime import datetime
import re

class AutoWebCrawler:
    def __init__(self, base_url, verbose=True, download_dir="downloads"):
        self.base_url = base_url
        self.domain = urlparse(base_url).netloc
        self.visited_urls = set()
        self.results = []
        self.verbose = verbose
        self.download_dir = f"./sample_result/{self.domain}_{download_dir}"
        self.file_extensions = {
            'images': ['.jpg', '.jpeg', '.png', '.webp'],
            'documents': ['.pdf', '.doc', '.docx', '.xlsx', '.xls', '.ppt', '.pptx'],
            'videos': ['.mp4', '.avi', '.mov', '.wmv']
        }
        
        for dir_type in ['images', 'documents', 'videos']:
            os.makedirs(os.path.join(self.download_dir, dir_type), exist_ok=True)
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

    async def extract_links(self, content, current_url):
        links = set()
        
        # 마크다운 링크 형식 [text](url) 파싱
        urls = re.findall(r'\[([^\]]*)\]\(([^)]+)\)', content)
        for _, url in urls:
            absolute_url = urljoin(current_url, url)
            if self.should_crawl(absolute_url):
                links.add(absolute_url)
                
        return links

    def should_crawl(self, url):
        if url in self.visited_urls:
            return False
            
        parsed_url = urlparse(url)
        if parsed_url.netloc != self.domain:
            return False
            
        excluded_extensions = ['.gif', '.zip']
        if any(url.lower().endswith(ext) for ext in excluded_extensions):
            return False
            
        return True

    def get_file_type(self, url):
        ext = os.path.splitext(url)[1].lower()
        for file_type, extensions in self.file_extensions.items():
            if ext in extensions:
                return file_type
        return None

    async def download_file(self, url, session):
        file_type = self.get_file_type(url)
        if not file_type:
            return None

        try:
            async with session.get(url) as response:
                if response.status == 200:
                    filename = unquote(os.path.basename(urlparse(url).path))
                    save_path = os.path.join(self.download_dir, file_type, filename)
                    
                    content = await response.read()
                    with open(save_path, 'wb') as f:
                        f.write(content)
                    
                    self.save_results()

                    self.logger.info(f"Downloaded: {filename}")
                    return {
                        'url': url,
                        'local_path': save_path,
                        'file_type': file_type,
                        'size': len(content)
                    }
                    
        except Exception as e:
            self.logger.error(f"Error downloading {url}: {str(e)}")
        return None

    async def extract_file_links(self, content, current_url):
        file_links = set()
        
        # 마크다운 링크, HTML href 속성, HTML src 속성 체크
        patterns = [
            r'\[([^\]]*)\]\(([^)]+)\)',  
            r'href=["\'](.*?)["\']',      
            r'src=["\'](.*?)["\']'        
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, content)
            for match in matches:
                url = match[1] if isinstance(match, tuple) else match
                absolute_url = urljoin(current_url, url)
                if self.get_file_type(absolute_url):
                    file_links.add(absolute_url)
                    
        return file_links

    async def crawl_page(self, url, crawler, session):
        if url in self.visited_urls:
            return set(), []
            
        self.visited_urls.add(url)
        self.logger.info(f"Crawling: {url}")
        
        try:
            result = await crawler.arun(url=url)
            
            page_info = {
                'url': url,
                'content': result.markdown,
                'title': result.title if hasattr(result, 'title') else 'No Title',
                'crawled_at': datetime.now().isoformat()
            }
            
            file_links = await self.extract_file_links(result.markdown, url)
            
            download_tasks = [self.download_file(file_url, session) for file_url in file_links]
            downloaded_files = await asyncio.gather(*download_tasks)
            downloaded_files = [f for f in downloaded_files if f]
            
            page_info['downloaded_files'] = downloaded_files
            self.results.append(page_info)
            
            page_links = await self.extract_links(result.markdown, url)
            return page_links, downloaded_files
                
        except Exception as e:
            self.logger.error(f"Error crawling {url}: {str(e)}")
            return set(), []

    async def crawl(self, max_pages=None):
        async with AsyncWebCrawler(verbose=self.verbose) as crawler:
            async with aiohttp.ClientSession() as session:
                to_crawl = {self.base_url}
                total_downloaded = []
                
                while to_crawl and (max_pages is None or len(self.visited_urls) < max_pages):
                    current_batch = list(to_crawl)[:5]
                    tasks = [self.crawl_page(url, crawler, session) for url in current_batch]
                    results = await asyncio.gather(*tasks)
                    
                    new_links = set()
                    for links, downloads in results:
                        new_links.update(links)
                        total_downloaded.extend(downloads)
                    
                    to_crawl = (to_crawl.union(new_links) - self.visited_urls) - set(current_batch)
                    
                    self.logger.info(
                        f"Crawled: {len(self.visited_urls)} pages, "
                        f"Downloaded: {len(total_downloaded)} files, "
                        f"Remaining: {len(to_crawl)}"
                    )
                    
                    await asyncio.sleep(1)

    def save_results(self, filename='crawler_results.json'):
        directory=os.path.join(self.download_dir, filename)
        with open(directory, 'w', encoding='utf-8') as f:
            json.dump({
                'base_url': self.base_url,
                'total_pages_crawled': len(self.visited_urls),
                'crawl_date': datetime.now().isoformat(),
                'results': self.results
            }, f, ensure_ascii=False, indent=2)

async def main():
    base_url = "https://finance.naver.com/"
    crawler = AutoWebCrawler(base_url, verbose=True, download_dir="site_downloads")
    await crawler.crawl(max_pages=50)
    # crawler.save_results()

if __name__ == "__main__":
    asyncio.run(main())