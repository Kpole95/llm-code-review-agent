function mergeConfig(target, source) {
  for (const key in source) {
    if (typeof source[key] === "object") {
      target[key] = mergeConfig(target[key] || {}, source[key]);
    } else {
      target[key] = source[key];
    }
  }
  return target;
}
 
function applyUserSettings(defaults, userInput) {
  return mergeConfig(defaults, userInput);
}
