import markdown2
import re
import html

def extract_markdown(data):
    data = data#html.escape(data)
    # Define the pattern to search for
    pattern = r"```(\w*)\n([\s\S]*?)\n```"

    # Define the replacement pattern
    replacement = r'<pre><code class="\1">\2</code></pre>'

    # Perform the replacement
    modified_content = re.sub(pattern, replacement, data)
    
    pattern = r"!\[(.*?)\][ ]*\((.*?)\)"
    replacement = r'![\1](\2) <figcaption>\1</figcaption>'
    modified_content = re.sub(pattern, replacement, modified_content)
    

    # # Regular expression pattern to find URLs with varying schemes
    # modified_content = re.sub(r'!\[(.*?)\]\((.*?)\)', r' ![\1](\2) ', modified_content)
    # matches = re.finditer(r'(\(?\s*https?://\S+\s*\)?)', modified_content)
    # formated_text = modified_content
    # for mth in matches:
    #     url = mth.group(1)
    #     if not re.match(r'(\(.*?\))', url):
    #         formated_text = formated_text.replace(url, f' [{url}]() ')
    # modified_content = formated_text

    
    return markdown2.markdown(modified_content).replace('<hr />', '<div class="separator"><span>• • •</span></div>')

if __name__ == '__main__':
    with open('upload.md', 'r', encoding='utf-8') as file:
        markdown_text = file.read()

    # Convert Markdown to HTML
    html_output = extract_markdown(markdown_text)

    # Print or save the HTML output
    print(html_output)
    
    
    with open('upload.html', 'w', encoding='utf-8') as file:
        file.write(html_output)
    