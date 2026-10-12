/* GACHA WARS – publisher verified Wuthering Waves Ver.3.5 Reverb selector. */
function applyWw2026ReverbOfficial(rows,d){
 if(!d||d.schema!=="gacha-wars-ww-2026-reverb-official-v1"||d.verification!=="official"||d.date!=="2026-07-10"||d.version_group!=="Ver.3.5"||
  !Array.isArray(d.selectable_resonators)||d.selectable_resonators.length!==6||!Array.isArray(d.character_four)||d.character_four.length!==3||
  !Array.isArray(d.selectable_weapons)||d.selectable_weapons.length!==6||!Array.isArray(d.weapon_four)||d.weapon_four.length!==3)
  throw Error("鳴潮リバーブ履歴の形式・数量不正");
 if(d.character_source!=="https://wutheringwaves.kurogames.com/en/main/news/detail/5065"||d.weapon_source!=="https://wutheringwaves.kurogames.com/en/main/news/detail/5076")throw Error("KURO出典不一致");
 if([d.selectable_resonators,d.selectable_weapons,d.weapon_four].some(a=>new Set(a).size!==a.length)||new Set(d.character_four.map(x=>x.id)).size!==3)throw Error("リバーブ候補が重複");
 const found=new Map(rows.map(x=>[x.id,x])),changes=new Map();
 for(const x of d.character_four){
  const old=found.get(x.id);
  if(!old||old.game!=="ww"||old.type!=="character"||old.date!==d.date||old.banner_type!=="reverb_convene_four_star"||old.rarity!==4||old.verification!=="secondary"||old.version!==x.name||old.featured_five_star!==x.previous_featured_five_star)throw Error("既存共鳴者のID・名前・日付不一致");
  changes.set(x.id,{...old,featured_five_star:"リバーブ★5選択式（6名）",selectable_five_star:d.selectable_resonators,event_banner_name:d.character_banner,verification:"official",source_url:d.character_source,source_title:"KURO GAMES公式・Starpath Reverbs",date_basis:d.date_basis,review_note:"公式の★5共鳴者6名から1名を選択する共通集音。★4対象は卜霊・散華・秧秧。"});
 }
 const base={game:"ww",type:"weapon",date:d.date,phase:"first",version_group:d.version_group,event_kind:"featured_banner",weapon_banner_group:d.weapon_banner,featured_five_star:"リバーブ★5選択式（6武器）",reverb_selectable:true,verification:"official",source_url:d.weapon_source,source_title:"KURO GAMES公式・Tideforge Reverbs",date_basis:d.date_basis,corroborating_sources:[d.maintenance_source],review_note:"公式Tideforge Reverbsは★5武器6種類から1本を選択できる単一集音。共有★4PUは3種類。6本を別ガチャと誤算しない。"};
 const extras=[];
 [[5,"ww_weapon_reverb_five",d.selectable_weapons],[4,"ww_weapon_reverb_four",d.weapon_four]].forEach(([rarity,banner_type,names])=>names.forEach((version,i)=>{
  if(typeof version!=="string"||!version.trim())throw Error("武器名不正");
  const id="ww-reverb-2026-07-10-"+rarity+"-"+(i+1);
  if(found.has(id))throw Error("武器登録IDが重複");
  extras.push({...base,id,version,rarity,banner_type});
 }));
 if(extras.length!==9||changes.size!==3)throw Error("リバーブ補完数量に誤り");
 return {primary:rows.map(x=>changes.get(x.id)||x),extras,upgraded:changes.size};
}
