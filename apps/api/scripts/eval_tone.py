# apps/api/scripts/eval_tone.py

import sys

POSITIVE_PHRASES = ["你看", "是不是", "别担心", "直观", "手拉手", "模型", "勾股定理", "注意", "试一试"]
NEGATIVE_TERMS = ["拓扑", "微分", "流形", "同构", "线性代数", "张量", "仿射", "射影几何"]

def eval_text(text):
    score = 0
    found_pos = []
    found_neg = []
    
    for p in POSITIVE_PHRASES:
        if p in text:
            score += 1
            found_pos.append(p)
            
    for n in NEGATIVE_TERMS:
        if n in text:
            score -= 5
            found_neg.append(n)
            
    return score, found_pos, found_neg

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python eval_tone.py 'text to evaluate'")
        sys.exit(1)
        
    text = sys.argv[1]
    score, pos, neg = eval_text(text)
    print(f"Score: {score}")
    print(f"Positive: {pos}")
    print(f"Negative: {neg}")
    
    # Simple pass criteria: no negative terms, and ideally some positive tone.
    # We don't strictly enforce positive score for short texts, but we strictly ban negative terms.
    if not neg:
        print("PASS")
        sys.exit(0)
    else:
        print("FAIL")
        sys.exit(1)
