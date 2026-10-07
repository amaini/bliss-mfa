"""Apply the reviewed native HTTP framing fix to the bundled engine client.

The installed credential-provider client receives the equivalent PowerShell patch.
Exact anchors fail closed when upstream source changes.
"""

from pathlib import Path
import re


def patch(path: Path):
    text = path.read_bytes().decode("latin-1").replace("\r\n", "\n")
    context_start = text.index("_default_ssl_context = array(")
    context_end = text.index("'disable_compression'", context_start)
    prefix = text[:context_end]
    trust = re.compile(r"('verify_peer(?:_name)?'\s*=>\s*)(false|true)")
    if len(trust.findall(prefix)) != 2:
        raise ValueError("Unexpected multiOTP TLS defaults")
    text = trust.sub(r"\g<1>true", prefix) + text[context_end:]
    request_marker = "// Bliss: send exactly Content-Length bytes."
    if request_marker not in text:
        post = '                  fputs($fp, $content_to_post);\n                  fputs($fp, "\\r\\n");'
        length = '                  fputs($fp, "Content-Length: ".mb_strlen($content_to_post)."\\r\\n");'
        if text.count(post) != 1 or text.count(length) != 1:
            raise ValueError("Unexpected native request framing")
        text = text.replace(
            post,
            "                  "
            + request_marker
            + "\n                  fputs($fp, $content_to_post);",
        )
        text = text.replace(length, length.replace("mb_strlen", "strlen"))
    marker = "// Bliss: read the complete framed HTTP body without waiting for TLS EOF."
    if marker in text:
        path.write_bytes(text.encode("latin-1"))
        return
    initialization = "                  $last_length = 0;"
    read = "                      $reply.= fgets($fp, 1024);"
    metadata = "                      $info = stream_get_meta_data($fp);"
    anchors = [initialization, read, metadata]
    if any(text.count("\n" + a + "\n") != 1 for a in anchors):
        raise ValueError("Unexpected multiOTP HTTP read loop; refusing ambiguous patch")
    text = text.replace(
        "\n" + initialization + "\n",
        "\n" + initialization + "\n                  $expected_reply_length = NULL;\n",
    )
    text = text.replace(
        "\n" + read + "\n",
        """
                      // Bliss: read the complete framed HTTP body without waiting for TLS EOF.
                      if (NULL === $expected_reply_length) {
                          $reply.= fgets($fp, 1024);
                      } else {
                          $remaining = $expected_reply_length - strlen($reply);
                          if ($remaining <= 0) { break; }
                          $reply.= fread($fp, min(8192, $remaining));
                      }
""",
    )
    text = text.replace(
        "\n" + metadata + "\n",
        "\n"
        + metadata
        + """
                      $header_end = strpos($reply, "\\r\\n\\r\\n");
                      if (FALSE !== $header_end) {
                          $header = substr($reply, 0, $header_end)."\\r\\n";
                          if (preg_match('/\\r\\nContent-Length:\\s*([0-9]+)\\s*\\r\\n/i', $header, $length)) {
                              $expected_reply_length = $header_end + 4 + intval($length[1]);
                              if (strlen($reply) >= $expected_reply_length) {
                                  $reply = substr($reply, 0, $expected_reply_length);
                                  $info['timed_out'] = FALSE;
                                  break;
                              }
                          }
                      }
""",
    )
    path.write_bytes(text.encode("latin-1"))
