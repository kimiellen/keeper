//! 拼音工具
//!
//! 计算书签名称的拼音首字母和完整拼音。

use pinyin::ToPinyin;

/// 计算拼音首字母
///
/// 中文：取拼音首字母（"百度" -> "bd"）
/// 英文 CamelCase：取大写字母（"GitHub" -> "gh"）
/// 英文小写：取首字母（"github" -> "g"）
///
/// # Examples
/// ```
/// use keeper::utils::pinyin::compute_initials;
/// assert_eq!(compute_initials("百度"), "bd");
/// assert_eq!(compute_initials("GitHub"), "gh");
/// assert_eq!(compute_initials("github"), "g");
/// assert_eq!(compute_initials("GitHub工作"), "ghgz");
/// ```
pub fn compute_initials(name: &str) -> String {
    let mut result = String::new();
    let mut i = 0;
    let chars: Vec<char> = name.chars().collect();

    while i < chars.len() {
        let ch = chars[i];
        
        // 中文字符
        if ('\u{4e00}'..='\u{9fff}').contains(&ch) {
            // 获取拼音首字母
            if let Some(pinyin) = ch.to_pinyin() {
                result.push_str(pinyin.first_letter());
            }
            i += 1;
        }
        // 英文字母
        else if ch.is_ascii_alphabetic() {
            let mut j = i;
            // 收集连续的英文字母
            while j < chars.len() && chars[j].is_ascii_alphabetic() {
                j += 1;
            }
            
            let segment: String = chars[i..j].iter().collect();
            
            // 提取大写字母
            let uppers: Vec<char> = segment.chars().filter(|c| c.is_uppercase()).collect();
            
            if !uppers.is_empty() {
                // CamelCase: 取所有大写字母
                for c in uppers {
                    result.push(c.to_ascii_lowercase());
                }
            } else {
                // 全小写: 取首字母
                result.push(segment.chars().next().unwrap().to_ascii_lowercase());
            }
            
            i = j;
        }
        else {
            i += 1;
        }
    }

    // 限制长度
    result.truncate(50);
    result
}

/// 计算完整拼音
///
/// 将中文字符转换为完整拼音（无音调）。
/// 非中文字符保持原样。
pub fn compute_full_pinyin(name: &str) -> String {
    let mut result = String::new();
    
    for ch in name.chars() {
        // 中文字符
        if ('\u{4e00}'..='\u{9fff}').contains(&ch) {
            if let Some(pinyin) = ch.to_pinyin() {
                // 获取拼音（plain 表示无音调）
                result.push_str(pinyin.plain());
            }
        }
        // 英文字母转为小写
        else if ch.is_ascii_alphabetic() {
            result.push(ch.to_ascii_lowercase());
        }
        // 其他字符忽略
    }
    
    result
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_compute_initials_chinese() {
        assert_eq!(compute_initials("百度"), "bd");
        assert_eq!(compute_initials("阿里巴巴"), "albb");
        assert_eq!(compute_initials("腾讯科技"), "txkj");
    }

    #[test]
    fn test_compute_initials_camelcase() {
        assert_eq!(compute_initials("GitHub"), "gh");
        assert_eq!(compute_initials("MySQL"), "msql");
        assert_eq!(compute_initials("iPhone"), "p");
    }

    #[test]
    fn test_compute_initials_lowercase() {
        assert_eq!(compute_initials("github"), "g");
        assert_eq!(compute_initials("twitter"), "t");
    }

    #[test]
    fn test_compute_initials_mixed() {
        assert_eq!(compute_initials("GitHub工作"), "ghgz");
        assert_eq!(compute_initials("我的GitHub"), "wdgh");
    }

    #[test]
    fn test_compute_initials_with_numbers() {
        assert_eq!(compute_initials("Test123"), "t");
        assert_eq!(compute_initials("Test 123"), "t");
    }

    #[test]
    fn test_compute_full_pinyin() {
        assert_eq!(compute_full_pinyin("百度"), "baidu");
        assert_eq!(compute_full_pinyin("GitHub"), "github");
        assert_eq!(compute_full_pinyin("我的GitHub"), "wodegithub");
    }
}
