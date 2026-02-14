
import re
from typing import List, Dict, Any
from schemas import ExtractedTZData, KeyFeaturesDetails, SourceText

def split_markdown(text: str, max_chars: int = 15000, overlap: int = 0) -> List[str]:
    """
    Splits markdown text into chunks, respecting headers where possible.
    Includes overlap calculation.
    """
    if len(text) <= max_chars:
        return [text]

    chunks = []
    
    # Simple line-based splitter with overlap
    lines = text.split('\n')
    current_chunk_lines = []
    current_length = 0
    
    i = 0
    while i < len(lines):
        line = lines[i]
        line_len = len(line) + 1 # +1 for newline
        
        # If adding this line exceeds max_chars
        if current_length + line_len > max_chars:
            if current_chunk_lines:
                # Save current chunk
                chunks.append("\n".join(current_chunk_lines))
                
                # Calculate overlap: keep last N lines that fit into `overlap` chars
                overlap_buffer = []
                overlap_len = 0
                # Go backwards
                for prev_line in reversed(current_chunk_lines):
                    if overlap_len + len(prev_line) + 1 <= overlap:
                         overlap_buffer.insert(0, prev_line)
                         overlap_len += len(prev_line) + 1
                    else:
                        break
                
                current_chunk_lines = overlap_buffer
                current_length = overlap_len
            
            # If the single line is huge (larger than max_chars), force split it
            if line_len > max_chars:
                 # If we have overlap content, it's already in current_chunk_lines. 
                 # But since this line is huge, we might as well just append it as a separate chunk(s) 
                 # or append it and split immediately.
                 # Let's simplify: just add it, it will create a big chunk, but better than losing it.
                 # Or split character wise.
                 range_steps = range(0, len(line), max_chars)
                 for k in range_steps:
                     sub_line = line[k : k + max_chars]
                     chunks.append(sub_line)
                 
                 # Reset wrapper
                 current_chunk_lines = []
                 current_length = 0
                 i += 1
                 continue
                 
        current_chunk_lines.append(line)
        current_length += line_len
        i += 1
        
    if current_chunk_lines:
        chunks.append("\n".join(current_chunk_lines))
        
    return chunks

def merge_extracted_data(data_list: List[ExtractedTZData]) -> ExtractedTZData:
    """
    Merges multiple ExtractedTZData objects into one.
    Improvements:
    - Client Name: Filter 'Unknown', pick most frequent or longest.
    - Project Type: Most frequent.
    """
    start_data = ExtractedTZData()
    
    # Helper for voting
    from collections import Counter
    
    def get_best_value(items, invalid_values=None):
        if invalid_values is None: 
            invalid_values = []
        
        # Filter
        valid_items = [
            item for item in items 
            if item.text and item.text.strip() not in invalid_values
        ]
        
        if not valid_items:
            return None
            
        # Count occurrences of normalized text
        values = [i.text.strip() for i in valid_items]
        counts = Counter(values)
        
        # Get most common
        most_common_text, _ = counts.most_common(1)[0]
        
        # Find the original object that matches this text (prefer one with source if possible)
        for item in valid_items:
            if item.text.strip() == most_common_text:
                return item
        return valid_items[0]

    # 1. Merge Client Name
    bad_names = ["Unknown Client", "Unknown", "Не указан", "Нет", "N/A", "Client Name"]
    best_client = get_best_value([d.client_name for d in data_list], bad_names)
    if best_client:
        start_data.client_name = best_client
        
    # 2. Merge Project Essence (Smart Selection)
    candidates_essence = [d.project_essence for d in data_list if d.project_essence.text not in ["Unknown Essence", "", "N/A"]]
    if candidates_essence:
        # Heuristic: Prefer "denser" text (more capitalized words / length ratio) + length
        # But for now, let's just avoid "Intro" spam.
        
        def score_essence(st: SourceText) -> int:
            t = st.text
            score = len(t)
            # Penalize generic intros if they dominate (simple heuristic)
            if t.strip().lower().startswith("this document") or t.strip().lower().startswith("данный документ"):
                score -= 50
            return score
            
        start_data.project_essence = max(candidates_essence, key=score_essence)
        
    # 3. Merge Project Type (Voting)
    candidates_type = [d.project_type for d in data_list]
    best_type = get_best_value(candidates_type, ["Other", "Unknown", ""])
    if best_type:
        start_data.project_type = best_type

    # 4. Merge Lists (business_goals, tech_stack, client_integrations)
    def merge_source_text_lists(lists: List[List[SourceText]]) -> List[SourceText]:
        seen_map = {} # text -> index in merged list
        merged = []
        
        for l in lists:
            for item in l:
                clean_text = item.text.strip() # Case sensitive or insensitive? Let's keep sensitive for now but strip
                if not clean_text:
                    continue
                
                key = clean_text.lower()
                if key not in seen_map:
                    seen_map[key] = len(merged)
                    merged.append(item)
                    
        return merged

    start_data.business_goals = merge_source_text_lists([d.business_goals for d in data_list])
    start_data.tech_stack = merge_source_text_lists([d.tech_stack for d in data_list])
    start_data.client_integrations = merge_source_text_lists([d.client_integrations for d in data_list])
    
    # 5. Merge Key Features (KeyFeaturesDetails)
    kf_merged = KeyFeaturesDetails(
        modules=merge_source_text_lists([d.key_features.modules for d in data_list]),
        screens=merge_source_text_lists([d.key_features.screens for d in data_list]),
        reports=merge_source_text_lists([d.key_features.reports for d in data_list]),
        integrations=merge_source_text_lists([d.key_features.integrations for d in data_list]),
        nfr=merge_source_text_lists([d.key_features.nfr for d in data_list]),
    )
    start_data.key_features = kf_merged
    
    return start_data
