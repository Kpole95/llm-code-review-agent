function renderComment(comment) {
  const p = document.createElement("p");
  p.textContent = comment.text;
  document.getElementById("comments").appendChild(p);
}
